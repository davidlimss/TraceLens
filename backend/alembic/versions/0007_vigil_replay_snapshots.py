"""Persist immutable VIGIL run snapshots for replay and run diff.

Revision ID: 0007_vigil_replay_snapshots
Revises: 0006_production_hardening
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0007_vigil_replay_snapshots"
down_revision = "0006_production_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "agent_run_snapshots" in inspector.get_table_names():
        return
    op.create_table(
        "agent_run_snapshots",
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("agent_runs.agent_run_id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_type", sa.String(32), nullable=False, server_default="completion"),
        sa.Column("replay_mode", sa.String(32), nullable=True),
        sa.Column("snapshot_version", sa.String(32), nullable=False, server_default="run-snapshot-v1"),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_run_snapshots_run_id", "agent_run_snapshots", ["agent_run_id"])
    op.create_index("ix_agent_run_snapshots_case_id", "agent_run_snapshots", ["case_id"])
    op.create_index("ix_agent_run_snapshots_source_run_id", "agent_run_snapshots", ["source_run_id"])
    op.create_index("ix_agent_run_snapshots_hash", "agent_run_snapshots", ["snapshot_hash"])


def downgrade() -> None:
    raise RuntimeError("VIGIL replay snapshots are intentionally not downgraded")
