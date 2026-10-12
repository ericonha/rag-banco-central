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
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.config import get_settings
from app.db.chunks import get_chunks_needing_embedding
from app.db.session import get_conn
from app.rag.answering import answer_question
from app.rag.retrieval import retrieve_chunks

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


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Answer a question using RAG.
    
    Retrieves relevant chunks from the database and calls Claude API.
    """
    if not settings.embedding_model or not settings.anthropic_api_key:
        raise HTTPException(
            status_code=500, detail="Embedding model or API key not configured"
        )

    try:
        async with get_conn() as conn:
            # Retrieve relevant chunks
            chunks = await retrieve_chunks(
                conn,
                question=request.question,
                embedding_model=settings.embedding_model,
                embedding_dim=settings.embedding_dim,
                k=5,
            )

            if not chunks:
                return ChatResponse(
                    answer="No relevant documents found." if request.language == "en"
                    else "Nenhum documento relevante encontrado.",
                    sources=[],
                    retrieved_chunks=0,
                )

            # Generate answer
            answer_text, sources = answer_question(
                question=request.question,
                chunks=chunks,
                language=request.language,
                anthropic_api_key=settings.anthropic_api_key,
                anthropic_model=settings.anthropic_model or "claude-opus-5-5",
            )

            logger.info(
                "Answer generated: language=%s sources=%d",
                request.language,
                len(sources),
            )

            return ChatResponse(
                answer=answer_text,
                sources=[SourceRef(**s) for s in sources],
                retrieved_chunks=len(chunks),
            )

    except Exception as exc:
        logger.error("Error processing question: %s", exc)
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


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> dict[str, Any]:
    """
    Get conversation history (placeholder for Phase 5).
    """
    # TODO: Implement after Phase 6 (conversation tracking)
    return {"conversation_id": conversation_id, "messages": []}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
