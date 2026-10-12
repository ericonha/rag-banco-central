"""Add cost_usd to query_logs

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS cost_usd NUMERIC(12, 6)")


def downgrade() -> None:
    op.execute("ALTER TABLE query_logs DROP COLUMN IF EXISTS cost_usd")
