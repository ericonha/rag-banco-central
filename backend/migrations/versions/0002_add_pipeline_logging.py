"""Add pipeline logging tables (pipeline_runs, pipeline_events, query_logs)

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create pipeline logging tables for observability."""
    
    # pipeline_runs: track each stage (scrape, chunk, embed) execution
    op.execute("""
        CREATE TABLE pipeline_runs (
            id           BIGSERIAL PRIMARY KEY,
            stage        TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'running' 
                         CHECK (status IN ('running', 'ok', 'done_with_errors', 'failed')),
            started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at  TIMESTAMPTZ,
            duration_ms  INTEGER,
            params       JSONB,
            items_total  INTEGER DEFAULT 0,
            items_ok     INTEGER DEFAULT 0,
            items_failed INTEGER DEFAULT 0,
            error        TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX pipeline_runs_stage_started_idx ON pipeline_runs (stage, started_at DESC)")
    
    # pipeline_events: detailed logs for each failure or important item
    op.execute("""
        CREATE TABLE pipeline_events (
            id           BIGSERIAL PRIMARY KEY,
            run_id       BIGINT NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
            level        TEXT NOT NULL 
                         CHECK (level IN ('info', 'warning', 'error')),
            document_id  BIGINT REFERENCES documents(id) ON DELETE SET NULL,
            chunk_id     BIGINT REFERENCES chunks(id) ON DELETE SET NULL,
            message      TEXT NOT NULL,
            details      JSONB,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX pipeline_events_run_idx ON pipeline_events (run_id)")
    op.execute("CREATE INDEX pipeline_events_level_idx ON pipeline_events (level)")
    
    # query_logs: track all RAG queries with metrics
    op.execute("""
        CREATE TABLE query_logs (
            id                      BIGSERIAL PRIMARY KEY,
            question                TEXT NOT NULL,
            answer                  TEXT,
            retrieved               JSONB,
            top_k                   INTEGER DEFAULT 5,
            embedding_model         TEXT,
            llm_model               TEXT,
            tokens_in               INTEGER,
            tokens_out              INTEGER,
            latency_retrieval_ms    INTEGER,
            latency_llm_ms          INTEGER,
            latency_total_ms        INTEGER,
            status                  TEXT DEFAULT 'ok' 
                                   CHECK (status IN ('ok', 'error')),
            error                   TEXT,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX query_logs_created_at_idx ON query_logs (created_at DESC)")
    op.execute("CREATE INDEX query_logs_status_idx ON query_logs (status)")


def downgrade() -> None:
    """Remove pipeline logging tables."""
    for table in ("query_logs", "pipeline_events", "pipeline_runs"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
