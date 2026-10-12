"""Message feedback and answer grounding

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS feedback SMALLINT CHECK (feedback IN (-1, 1))")
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS feedback_comment TEXT")
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS feedback_at TIMESTAMPTZ")
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS grounding JSONB")
    op.execute("ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS grounding JSONB")
    op.execute(
        "CREATE INDEX IF NOT EXISTS messages_feedback_idx ON messages (feedback_at DESC) "
        "WHERE feedback IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS messages_feedback_idx")
    op.execute("ALTER TABLE query_logs DROP COLUMN IF EXISTS grounding")
    for col in ("grounding", "feedback_at", "feedback_comment", "feedback"):
        op.execute(f"ALTER TABLE messages DROP COLUMN IF EXISTS {col}")
