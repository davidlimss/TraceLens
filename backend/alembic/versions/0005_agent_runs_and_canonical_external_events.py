"""durable agent traces and canonical external event projections

Revision ID: 0005_agent_runs_and_canonical_external_events
Revises: 0004_external_evidence
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0005_agent_durable_events"
down_revision = "0004_external_evidence"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}


def _add_column(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def upgrade() -> None:
    # A local Event is linked to an upload file. An external canonical event
    # instead points to an immutable ExternalEvidence snapshot.
    _add_column("events", sa.Column("external_evidence_id", postgresql.UUID(as_uuid=True), nullable=True))
    _add_column("events", sa.Column("event_origin", sa.String(32), nullable=False, server_default="local"))
    op.alter_column("events", "evidence_file_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    event_indexes = _indexes("events")
    if "ix_events_external_evidence_id" not in event_indexes:
        op.create_index("ix_events_external_evidence_id", "events", ["external_evidence_id"])
    if "ix_events_event_origin" not in event_indexes:
        op.create_index("ix_events_event_origin", "events", ["event_origin"])
    foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys("events")
    has_external_fk = any("external_evidence_id" in (item.get("constrained_columns") or []) for item in foreign_keys)
    if not has_external_fk:
        op.create_foreign_key("fk_events_external_evidence_id", "events", "external_evidence",
                              ["external_evidence_id"], ["evidence_id"], ondelete="RESTRICT")
    unique_constraints = {item["name"] for item in sa.inspect(op.get_bind()).get_unique_constraints("events")}
    if "uq_events_external_evidence" not in unique_constraints:
        op.create_unique_constraint("uq_events_external_evidence", "events", ["external_evidence_id"])

    # Durable run metadata is deliberately separate from raw tool payloads.
    for name, column in (
        ("current_step", sa.Column("current_step", sa.Integer(), nullable=False, server_default="0")),
        ("cancel_requested", sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false())),
        ("stop_reason", sa.Column("stop_reason", sa.Text(), nullable=True)),
        ("prompt_version", sa.Column("prompt_version", sa.String(64), nullable=True)),
        ("model_version", sa.Column("model_version", sa.String(128), nullable=True)),
        ("graph_version", sa.Column("graph_version", sa.String(64), nullable=False, server_default="investigation-graph-v1")),
    ):
        if name not in _columns("agent_runs"):
            op.add_column("agent_runs", column)

    inspector = sa.inspect(op.get_bind())
    if "agent_steps" not in inspector.get_table_names():
        op.create_table(
            "agent_steps",
            sa.Column("agent_step_id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.agent_run_id", ondelete="CASCADE"), nullable=False),
            sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False),
            sa.Column("step_number", sa.Integer(), nullable=False),
            sa.Column("step_type", sa.String(32), nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="completed"),
            sa.Column("input_data", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("output_data", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("error_code", sa.String(64), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "ix_agent_steps_run_order" not in _indexes("agent_steps"):
        op.create_index("ix_agent_steps_run_order", "agent_steps", ["agent_run_id", "step_number", "agent_step_id"])

    inspector = sa.inspect(op.get_bind())
    if "evidence_ledgers" not in inspector.get_table_names():
        op.create_table(
            "evidence_ledgers",
            sa.Column("ledger_id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.agent_run_id", ondelete="CASCADE"), nullable=False),
            sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False),
            sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("evidence_kind", sa.String(32), nullable=False),
            sa.Column("source_tool", sa.String(128), nullable=False),
            sa.Column("reference_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("agent_run_id", "evidence_id", name="uq_evidence_ledger_run_evidence"),
        )
    if "ix_evidence_ledgers_run_id" not in _indexes("evidence_ledgers"):
        op.create_index("ix_evidence_ledgers_run_id", "evidence_ledgers", ["agent_run_id"])
    if "ix_evidence_ledgers_case_id" not in _indexes("evidence_ledgers"):
        op.create_index("ix_evidence_ledgers_case_id", "evidence_ledgers", ["case_id"])
    if "ix_evidence_ledgers_evidence_id" not in _indexes("evidence_ledgers"):
        op.create_index("ix_evidence_ledgers_evidence_id", "evidence_ledgers", ["evidence_id"])

    # Reinstall the immutability guard with the new canonical-reference fields.
    op.execute("""
    CREATE OR REPLACE FUNCTION prevent_event_evidence_mutation() RETURNS trigger AS $$
    BEGIN
      IF NEW.raw_log IS DISTINCT FROM OLD.raw_log
         OR NEW.raw_line_number IS DISTINCT FROM OLD.raw_line_number
         OR NEW.evidence_file_id IS DISTINCT FROM OLD.evidence_file_id
         OR NEW.external_evidence_id IS DISTINCT FROM OLD.external_evidence_id
         OR NEW.event_origin IS DISTINCT FROM OLD.event_origin THEN
        RAISE EXCEPTION 'event evidence fields are immutable';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    raise RuntimeError("Durable investigation state is intentionally not downgraded")
