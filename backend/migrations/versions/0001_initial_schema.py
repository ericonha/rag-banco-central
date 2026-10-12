"""initial schema

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Embedding dimension of intfloat/multilingual-e5-base (chosen in the Phase 0 spike).
# Changing the model to one with a different dimension needs a new migration + re-embedding.
EMBEDDING_DIM = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE documents (
            id           BIGSERIAL PRIMARY KEY,
            source       TEXT NOT NULL,
            url          TEXT NOT NULL UNIQUE,
            title        TEXT,
            doc_type     TEXT,
            published_at TIMESTAMPTZ,
            language     TEXT NOT NULL DEFAULT 'pt',
            content_hash TEXT NOT NULL,
            raw_text     TEXT NOT NULL,
            fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX documents_published_at_idx ON documents (published_at DESC)")
    op.execute("CREATE INDEX documents_doc_type_idx ON documents (doc_type)")

    op.execute(
        f"""
        CREATE TABLE chunks (
            id              BIGSERIAL PRIMARY KEY,
            document_id     BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index     INTEGER NOT NULL,
            text            TEXT NOT NULL,
            token_count     INTEGER,
            embedding       vector({EMBEDDING_DIM}),
            embedding_model TEXT,
            UNIQUE (document_id, chunk_index)
        )
        """
    )
    op.execute(
        "CREATE INDEX chunks_embedding_hnsw_idx ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.execute(
        """
        CREATE TABLE conversations (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            language   TEXT NOT NULL DEFAULT 'pt'
        )
        """
    )
    op.execute(
        """
        CREATE TABLE messages (
            id              BIGSERIAL PRIMARY KEY,
            conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content         TEXT NOT NULL,
            sources         JSONB,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX messages_conversation_idx ON messages (conversation_id, id)")

    op.execute(
        """
        CREATE TABLE ingest_runs (
            id          BIGSERIAL PRIMARY KEY,
            started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at TIMESTAMPTZ,
            status      TEXT NOT NULL DEFAULT 'running',
            new_docs    INTEGER NOT NULL DEFAULT 0,
            errors      TEXT
        )
        """
    )


def downgrade() -> None:
    for table in ("ingest_runs", "messages", "conversations", "chunks", "documents"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
