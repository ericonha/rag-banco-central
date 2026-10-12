"""
FastAPI application for BCB RAG chatbot.

Endpoints:
- POST /api/chat — answer questions (streamed via SSE)
- GET /api/conversations/{id} — conversation history
- GET /api/documents — latest ingested documents
- GET /api/health — health check
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.config import get_settings
from app.db.chunks import get_chunks_needing_embedding
from app.db.conversations import get_recent_history, save_exchange
from app.db.session import get_conn
from app.rag.answering import answer_question_with_usage
from app.rag.context import retrieval_query
from app.rag.pricing import compute_cost
from app.observability import log_query
from app.rag.retrieval import retrieve_chunks
from app.routes.admin import router as admin_router
from app.routes.conversations import router as conversations_router

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


class HealthResponse(BaseModel):
    """Response body for GET /api/health"""
    status: str
    timestamp: datetime
    embedding_model: str | None = None


# ============================================================================
# Middleware
# ============================================================================


class SimpleRateLimiter:
    """Basic per-IP rate limiting (in-memory, resets on restart)."""
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests: dict[str, list[float]] = {}

    def is_allowed(self, ip: str) -> bool:
        """Check if IP is within rate limit."""
        now = datetime.now(tz=timezone.utc).timestamp()
        minute_ago = now - 60

        # Clean old requests
        if ip in self.requests:
            self.requests[ip] = [t for t in self.requests[ip] if t > minute_ago]

        # Check limit
        if ip not in self.requests:
            self.requests[ip] = []

        if len(self.requests[ip]) < self.requests_per_minute:
            self.requests[ip].append(now)
            return True
        return False


rate_limiter = SimpleRateLimiter(requests_per_minute=30)


async def rate_limit_middleware(request: Request, call_next):
    """Rate limit by IP address."""
    ip = request.client.host
    if not rate_limiter.is_allowed(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting middleware
app.middleware("http")(rate_limit_middleware)

# Admin / observability routes (/api/admin/...)
app.include_router(admin_router)

# Conversation history (/api/conversations/...)
app.include_router(conversations_router)


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
) -> None:
    """Save the Q&A pair; a storage problem must never break the answer."""
    try:
        await save_exchange(
            conversation_id,
            language,
            question,
            answer,
            [s.model_dump(mode="json") for s in sources],
        )
    except Exception as exc:
        logger.error("Could not save conversation %s: %s", conversation_id, exc)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Answer a question using RAG.

    Retrieves relevant chunks from the database and calls Claude API.
    Every call (success, empty result or error) is recorded in query_logs.
    """
    if not settings.embedding_model or not settings.anthropic_api_key:
        raise HTTPException(
            status_code=500, detail="Embedding model or API key not configured"
        )

    top_k = 5
    llm_model = settings.anthropic_model or "claude-opus-5-5"
    conversation_id = _conversation_uuid(request.conversation_id)
    t_start = time.perf_counter()
    retrieval_ms: int | None = None
    llm_ms: int | None = None
    retrieved: list[dict[str, Any]] | None = None

    def _elapsed_ms(since: float) -> int:
        return int((time.perf_counter() - since) * 1000)

    # Earlier turns give the LLM context; a storage problem must never break the answer.
    try:
        history = await get_recent_history(conversation_id, settings.history_max_messages)
    except Exception as exc:
        logger.error("Could not load history for %s: %s", conversation_id, exc)
        history = []

    try:
        async with get_conn() as conn:
            # Retrieve relevant chunks (short follow-ups are expanded with the previous question)
            chunks = await retrieve_chunks(
                conn,
                question=retrieval_query(request.question, history),
                embedding_model=settings.embedding_model,
                embedding_dim=settings.embedding_dim,
                k=top_k,
            )
            retrieval_ms = _elapsed_ms(t_start)
            # score = cosine similarity (1 - cosine distance)
            retrieved = [
                {
                    "chunk_id": c["id"],
                    "document_id": c["document_id"],
                    "score": round(1 - float(c["distance"]), 4),
                }
                for c in chunks
            ]

            if not chunks:
                answer = (
                    "No relevant documents found." if request.language == "en"
                    else "Nenhum documento relevante encontrado."
                )
                await log_query(
                    question=request.question,
                    answer=answer,
                    retrieved=retrieved,
                    top_k=top_k,
                    embedding_model=settings.embedding_model,
                    llm_model=None,
                    latency_retrieval_ms=retrieval_ms,
                    latency_total_ms=_elapsed_ms(t_start),
                )
                await _persist_exchange(conversation_id, request.language, request.question, answer, [])
                return ChatResponse(
                    answer=answer,
                    sources=[],
                    retrieved_chunks=0,
                    conversation_id=str(conversation_id),
                )

            # Generate answer
            t_llm = time.perf_counter()
            answer_text, sources, usage = answer_question_with_usage(
                question=request.question,
                chunks=chunks,
                language=request.language,
                anthropic_api_key=settings.anthropic_api_key,
                anthropic_model=llm_model,
                history=history,
            )
            llm_ms = _elapsed_ms(t_llm)
            cost = compute_cost(
                usage["tokens_in"],
                usage["tokens_out"],
                settings.llm_price_input_per_mtok,
                settings.llm_price_output_per_mtok,
            )

            logger.info(
                "Answer generated: language=%s sources=%d",
                request.language,
                len(sources),
            )

            await log_query(
                question=request.question,
                answer=answer_text,
                retrieved=retrieved,
                top_k=top_k,
                embedding_model=settings.embedding_model,
                llm_model=llm_model,
                tokens_in=usage["tokens_in"],
                tokens_out=usage["tokens_out"],
                cost_usd=cost,
                latency_retrieval_ms=retrieval_ms,
                latency_llm_ms=llm_ms,
                latency_total_ms=_elapsed_ms(t_start),
            )

            source_refs = [SourceRef(**s) for s in sources]
            await _persist_exchange(
                conversation_id, request.language, request.question, answer_text, source_refs
            )
            return ChatResponse(
                answer=answer_text,
                sources=source_refs,
                retrieved_chunks=len(chunks),
                conversation_id=str(conversation_id),
            )

    except Exception as exc:
        logger.error("Error processing question: %s", exc)
        await log_query(
            question=request.question,
            answer=None,
            retrieved=retrieved,
            top_k=top_k,
            embedding_model=settings.embedding_model,
            llm_model=llm_model,
            latency_retrieval_ms=retrieval_ms,
            latency_llm_ms=llm_ms,
            latency_total_ms=_elapsed_ms(t_start),
            status="error",
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail=str(exc))


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
