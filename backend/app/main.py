"""
FastAPI application for BCB RAG chatbot.

Endpoints:
- POST /api/chat — answer questions
- POST /api/chat/stream — same, streamed via SSE
- POST /api/messages/{id}/feedback — thumbs up/down
- GET /api/conversations/{id} — conversation history
- GET /api/documents — latest ingested documents
- GET /api/health — health check
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field

from app.config import get_settings
from app.db.chunks import get_chunks_needing_embedding
from app.db.conversations import get_recent_history, save_exchange
from app.db.session import get_conn
from app.rag.answering import answer_question_with_usage, sources_from_chunks, stream_answer, truncation_notice
from app.rag.faithfulness import check_answer
from app.rag.context import retrieval_query
from app.ratelimit import RateLimiter, bucket_for, client_ip
from app.rag.pricing import compute_cost
from app.observability import log_query
from app.rag.retrieval import retrieve_chunks
from app.routes.admin import router as admin_router
from app.routes.conversations import router as conversations_router
from app.routes.feedback import admin_router as feedback_admin_router
from app.routes.feedback import router as feedback_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("api")

settings = get_settings()

# ============================================================================
# Request/Response models
# ============================================================================


class ChatRequest(BaseModel):
    """Request body for POST /api/chat"""
    question: str = Field(..., min_length=1, max_length=1000, description="The user's question")
    language: str = Field(default="pt", pattern="^(pt|en)$", description="Response language")
    conversation_id: str | None = Field(
        default=None, description="Existing conversation ID (for context)"
    )
    doc_type: str | None = Field(default=None, max_length=80, description="Only search this document type")
    regenerate_of: int | None = Field(default=None, description="Assistant message id being regenerated (replaced on save)")
    since_days: int | None = Field(default=None, ge=1, le=3650, description="Only documents from the last N days")


class DocumentRef(BaseModel):
    """Reference to an ingested document"""
    id: int
    title: str
    url: str
    published_at: datetime
    doc_type: str
    chunk_count: int


class SourceRef(BaseModel):
    """Source cited in an answer"""
    title: str
    url: str
    published_at: datetime
    doc_type: str
    chunk_text: str


class ChatResponse(BaseModel):
    """Response body for POST /api/chat"""
    answer: str
    sources: list[SourceRef]
    retrieved_chunks: int
    conversation_id: str | None = None
    message_id: int | None = None
    grounding: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    """Response body for GET /api/health"""
    status: str
    timestamp: datetime
    embedding_model: str | None = None


# ============================================================================
# Middleware
# ============================================================================


rate_limiter = RateLimiter(
    {
        "default": settings.rate_limit_per_minute,
        "chat": settings.rate_limit_chat_per_minute,
    }
)


async def rate_limit_middleware(request: Request, call_next):
    """Rate limit by client IP; chat endpoints have their own, lower budget."""
    if request.method == "OPTIONS" or request.url.path == "/api/health":
        return await call_next(request)  # CORS preflight and health probes are never limited
    ip = client_ip(
        request.headers,
        request.client.host if request.client else None,
        settings.rate_limit_trust_proxy,
    )
    bucket = bucket_for(request.method, request.url.path)
    allowed, retry_after = rate_limiter.check(ip, bucket)
    if not allowed:
        logger.warning("Rate limit hit: ip=%s bucket=%s", ip, bucket)
        return JSONResponse(
            status_code=429,
            content={"detail": f"Too many requests. Try again in {retry_after}s."},
            headers={"Retry-After": str(retry_after)},
        )
    return await call_next(request)


# ============================================================================
# Lifespan
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown."""
    logger.info("API starting up")
    yield
    logger.info("API shutting down")


# ============================================================================
# Create app
# ============================================================================


app = FastAPI(
    title="BCB RAG API",
    description="RAG chatbot over Banco Central do Brasil regulations",
    version="1.0.0",
    lifespan=lifespan,
)

# Middleware order matters: the last one added is the outermost. The rate limiter is added
# first so CORS wraps it and 429 responses still carry CORS headers (otherwise the browser
# reports a network error instead of "too many requests").
app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limit_middleware)

_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["http://localhost:3000"],
    allow_credentials=False,  # no cookies are used; also required for a "*" origin
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
    expose_headers=["Retry-After", "Content-Disposition"],
)

# Admin / observability routes (/api/admin/...)
app.include_router(admin_router)

# Conversation history (/api/conversations/...)
app.include_router(conversations_router)

# Answer feedback (/api/messages/{id}/feedback, /api/admin/feedback)
app.include_router(feedback_router)
app.include_router(feedback_admin_router)


# ============================================================================
# Endpoints
# ============================================================================


@app.get("/api/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(tz=timezone.utc),
        embedding_model=settings.embedding_model or None,
    )


def _conversation_uuid(raw: str | None) -> uuid.UUID:
    """Use the client's conversation id when it is a valid UUID, otherwise start a new one."""
    try:
        return uuid.UUID(raw) if raw else uuid.uuid4()
    except ValueError:
        return uuid.uuid4()


async def _persist_exchange(
    conversation_id: uuid.UUID,
    language: str,
    question: str,
    answer: str,
    sources: list[SourceRef],
    grounding: dict[str, Any] | None = None,
    replace_message_id: int | None = None,
) -> int | None:
    """Save the Q&A pair and return the assistant message id; storage problems never break the answer."""
    try:
        return await save_exchange(
            conversation_id,
            language,
            question,
            answer,
            [s.model_dump(mode="json") for s in sources],
            grounding,
            replace_message_id,
        )
    except Exception as exc:
        logger.error("Could not save conversation %s: %s", conversation_id, exc)
        return None


TOP_K = 5


def _check_config() -> None:
    if not settings.embedding_model or not settings.anthropic_api_key:
        raise HTTPException(
            status_code=500, detail="Embedding model or API key not configured"
        )


def _elapsed_ms(since: float) -> int:
    return int((time.perf_counter() - since) * 1000)


async def _load_history(
    conversation_id: uuid.UUID, regenerate_of: int | None = None
) -> list[dict[str, str]]:
    """Earlier turns give the LLM context; a storage problem must never break the answer."""
    try:
        return await get_recent_history(conversation_id, settings.history_max_messages, regenerate_of)
    except Exception as exc:
        logger.error("Could not load history for %s: %s", conversation_id, exc)
        return []


async def _retrieve(
    question: str,
    history: list[dict[str, str]],
    doc_type: str | None = None,
    since_days: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Hybrid retrieval (+ optional rerank). Returns (chunks, retrieved-for-log)."""
    async with get_conn() as conn:
        chunks = await retrieve_chunks(
            conn,
            question=retrieval_query(question, history),
            embedding_model=settings.embedding_model,
            embedding_dim=settings.embedding_dim,
            k=TOP_K,
            rerank_model=settings.rerank_model,
            rerank_candidates=settings.rerank_candidates,
            doc_type_filter=doc_type,
            since_days=since_days,
            pinned_limit=settings.pinned_chunks,
        )
    # score = cosine similarity (1 - cosine distance)
    retrieved = [
        {
            "chunk_id": c["id"],
            "document_id": c["document_id"],
            "score": round(1 - float(c["distance"]), 4),
        }
        for c in chunks
    ]
    return chunks, retrieved


def _no_docs_answer(language: str) -> str:
    return "No relevant documents found." if language == "en" else "Nenhum documento relevante encontrado."


def _grounding(answer: str, chunks: list[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        return check_answer(answer, [c["text"] for c in chunks])
    except Exception as exc:  # heuristic only; never break the answer
        logger.error("Faithfulness check failed: %s", exc)
        return None


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Answer a question using RAG.

    Retrieves relevant chunks from the database and calls Claude API.
    Every call (success, empty result or error) is recorded in query_logs.
    """
    _check_config()

    llm_model = settings.anthropic_model or "claude-opus-5-5"
    conversation_id = _conversation_uuid(request.conversation_id)
    t_start = time.perf_counter()
    retrieval_ms: int | None = None
    llm_ms: int | None = None
    retrieved: list[dict[str, Any]] | None = None

    history = await _load_history(conversation_id, request.regenerate_of)

    try:
        chunks, retrieved = await _retrieve(request.question, history, request.doc_type, request.since_days)
        retrieval_ms = _elapsed_ms(t_start)

        if not chunks:
            answer = _no_docs_answer(request.language)
            await log_query(
                question=request.question,
                answer=answer,
                retrieved=retrieved,
                top_k=TOP_K,
                embedding_model=settings.embedding_model,
                llm_model=None,
                latency_retrieval_ms=retrieval_ms,
                latency_total_ms=_elapsed_ms(t_start),
            )
            message_id = await _persist_exchange(
                conversation_id, request.language, request.question, answer, [],
                replace_message_id=request.regenerate_of,
            )
            return ChatResponse(
                answer=answer,
                sources=[],
                retrieved_chunks=0,
                conversation_id=str(conversation_id),
                message_id=message_id,
            )

        t_llm = time.perf_counter()
        answer_text, sources, usage = answer_question_with_usage(
            question=request.question,
            chunks=chunks,
            language=request.language,
            anthropic_api_key=settings.anthropic_api_key,
            anthropic_model=llm_model,
            history=history,
            max_tokens=settings.llm_max_tokens,
        )
        llm_ms = _elapsed_ms(t_llm)
        cost = compute_cost(
            usage["tokens_in"],
            usage["tokens_out"],
            settings.llm_price_input_per_mtok,
            settings.llm_price_output_per_mtok,
        )
        grounding = _grounding(answer_text, chunks)

        logger.info(
            "Answer generated: language=%s sources=%d", request.language, len(sources)
        )

        await log_query(
            question=request.question,
            answer=answer_text,
            retrieved=retrieved,
            top_k=TOP_K,
            embedding_model=settings.embedding_model,
            llm_model=llm_model,
            tokens_in=usage["tokens_in"],
            tokens_out=usage["tokens_out"],
            cost_usd=cost,
            grounding=grounding,
            latency_retrieval_ms=retrieval_ms,
            latency_llm_ms=llm_ms,
            latency_total_ms=_elapsed_ms(t_start),
        )

        source_refs = [SourceRef(**s) for s in sources]
        message_id = await _persist_exchange(
            conversation_id, request.language, request.question, answer_text, source_refs, grounding,
            replace_message_id=request.regenerate_of,
        )
        return ChatResponse(
            answer=answer_text,
            sources=source_refs,
            retrieved_chunks=len(chunks),
            conversation_id=str(conversation_id),
            message_id=message_id,
            grounding=grounding,
        )

    except Exception as exc:
        logger.error("Error processing question: %s", exc)
        await log_query(
            question=request.question,
            answer=None,
            retrieved=retrieved,
            top_k=TOP_K,
            embedding_model=settings.embedding_model,
            llm_model=llm_model,
            latency_retrieval_ms=retrieval_ms,
            latency_llm_ms=llm_ms,
            latency_total_ms=_elapsed_ms(t_start),
            status="error",
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail=str(exc))


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """
    Same pipeline as /api/chat, answer delivered as Server-Sent Events:
    `meta` (sources, conversation_id) -> `delta`* (text pieces) -> `done` (message_id, grounding, usage)
    or `error`. Logging and persistence happen after the last delta.
    """
    _check_config()

    llm_model = settings.anthropic_model or "claude-opus-5-5"
    conversation_id = _conversation_uuid(request.conversation_id)

    async def events() -> AsyncIterator[str]:
        t_start = time.perf_counter()
        retrieval_ms: int | None = None
        llm_ms: int | None = None
        retrieved: list[dict[str, Any]] | None = None
        parts: list[str] = []
        try:
            history = await _load_history(conversation_id, request.regenerate_of)
            chunks, retrieved = await _retrieve(request.question, history, request.doc_type, request.since_days)
            retrieval_ms = _elapsed_ms(t_start)

            if not chunks:
                answer = _no_docs_answer(request.language)
                yield _sse("meta", {
                    "conversation_id": str(conversation_id), "sources": [], "retrieved_chunks": 0,
                })
                yield _sse("delta", {"text": answer})
                await log_query(
                    question=request.question, answer=answer, retrieved=retrieved, top_k=TOP_K,
                    embedding_model=settings.embedding_model, llm_model=None,
                    latency_retrieval_ms=retrieval_ms, latency_total_ms=_elapsed_ms(t_start),
                )
                message_id = await _persist_exchange(
                    conversation_id, request.language, request.question, answer, [],
                replace_message_id=request.regenerate_of,
                )
                yield _sse("done", {"message_id": message_id, "grounding": None, "usage": None})
                return

            sources = [SourceRef(**s) for s in sources_from_chunks(chunks)]
            yield _sse("meta", {
                "conversation_id": str(conversation_id),
                "sources": [s.model_dump(mode="json") for s in sources],
                "retrieved_chunks": len(chunks),
            })

            usage: dict[str, int | None] = {"tokens_in": None, "tokens_out": None}
            t_llm = time.perf_counter()
            async for ev in stream_answer(
                question=request.question,
                chunks=chunks,
                language=request.language,
                anthropic_api_key=settings.anthropic_api_key,
                anthropic_model=llm_model,
                history=history,
                max_tokens=settings.llm_max_tokens,
            ):
                if ev["type"] == "delta":
                    parts.append(ev["text"])
                    yield _sse("delta", {"text": ev["text"]})
                elif ev["type"] == "usage":
                    usage = {"tokens_in": ev["tokens_in"], "tokens_out": ev["tokens_out"]}
                    if ev.get("truncated"):
                        notice = truncation_notice(request.language)
                        parts.append(notice)
                        yield _sse("delta", {"text": notice})
            llm_ms = _elapsed_ms(t_llm)

            answer_text = "".join(parts)
            cost = compute_cost(
                usage["tokens_in"], usage["tokens_out"],
                settings.llm_price_input_per_mtok, settings.llm_price_output_per_mtok,
            )
            grounding = _grounding(answer_text, chunks)
            await log_query(
                question=request.question, answer=answer_text, retrieved=retrieved, top_k=TOP_K,
                embedding_model=settings.embedding_model, llm_model=llm_model,
                tokens_in=usage["tokens_in"], tokens_out=usage["tokens_out"], cost_usd=cost,
                grounding=grounding, latency_retrieval_ms=retrieval_ms, latency_llm_ms=llm_ms,
                latency_total_ms=_elapsed_ms(t_start),
            )
            message_id = await _persist_exchange(
                conversation_id, request.language, request.question, answer_text, sources, grounding,
                replace_message_id=request.regenerate_of,
            )
            yield _sse("done", {"message_id": message_id, "grounding": grounding, "usage": usage})

        except Exception as exc:
            logger.error("Error streaming answer: %s", exc)
            await log_query(
                question=request.question, answer="".join(parts) or None, retrieved=retrieved,
                top_k=TOP_K, embedding_model=settings.embedding_model, llm_model=llm_model,
                latency_retrieval_ms=retrieval_ms, latency_llm_ms=llm_ms,
                latency_total_ms=_elapsed_ms(t_start), status="error", error=str(exc),
            )
            yield _sse("error", {"detail": str(exc)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/documents", response_model=list[DocumentRef])
async def list_documents(limit: int = 20) -> list[DocumentRef]:
    """
    List recently ingested documents.
    """
    try:
        async with get_conn() as conn:
            rows = await (
                await conn.execute(
                    """
                    SELECT d.id, d.title, d.url, d.published_at, d.doc_type,
                           COUNT(c.id) as chunk_count
                    FROM documents d
                    LEFT JOIN chunks c ON d.id = c.document_id
                    GROUP BY d.id, d.title, d.url, d.published_at, d.doc_type
                    ORDER BY d.published_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            ).fetchall()

            return [DocumentRef(**dict(row)) for row in rows]

    except Exception as exc:
        logger.error("Error listing documents: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
