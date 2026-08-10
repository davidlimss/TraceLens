"""Complete the schema used by the production runtime.

Revision ID: 0006_production_hardening
Revises: 0005_agent_durable_events

The MVP temporarily added a few columns from the application lifespan.  This
revision makes those changes explicit so a production process never mutates
the schema while serving traffic.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_production_hardening"
down_revision = "0005_agent_durable_events"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}


def _add_column(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def upgrade() -> None:
    _add_column("events", sa.Column("session_id", sa.String(255), nullable=True))
    _add_column("events", sa.Column("timestamp_confidence", sa.Float(), nullable=False,
                                     server_default="1.0"))
    _add_column("events", sa.Column("timestamp_assumptions", sa.JSON(), nullable=False,
                                     server_default=sa.text("'[]'::json")))
    _add_column("events", sa.Column("year_source", sa.String(64), nullable=True))
    _add_column("events", sa.Column("timezone_source", sa.String(64), nullable=True))
    event_indexes = _indexes("events")
    if "ix_events_session_id" not in event_indexes:
        op.create_index("ix_events_session_id", "events", ["session_id"])

    _add_column("evidence_files", sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True))
    _add_column("evidence_files", sa.Column("parsing_mode", sa.String(32), nullable=False,
                                              server_default="strict"))
    _add_column("evidence_files", sa.Column("total_lines", sa.Integer(), nullable=False,
                                              server_default="0"))
    _add_column("evidence_files", sa.Column("processed_lines", sa.Integer(), nullable=False,
                                              server_default="0"))
    _add_column("evidence_files", sa.Column("parsed_events", sa.Integer(), nullable=False,
                                              server_default="0"))
    _add_column("evidence_files", sa.Column("malformed_lines", sa.Integer(), nullable=False,
                                              server_default="0"))
    _add_column("evidence_files", sa.Column("progress_percent", sa.Integer(), nullable=False,
                                              server_default="0"))
    _add_column("evidence_files", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    _add_column("evidence_files", sa.Column("retry_count", sa.Integer(), nullable=False,
                                              server_default="0"))
    _add_column("evidence_files", sa.Column("completeness_ratio", sa.Float(), nullable=False,
                                              server_default="1.0"))
    _add_column("evidence_files", sa.Column("integrity_status", sa.String(32), nullable=True))
    _add_column("evidence_files", sa.Column("integrity_verified_at", sa.DateTime(timezone=True), nullable=True))
    evidence_indexes = _indexes("evidence_files")
    if "ix_evidence_files_job_id" not in evidence_indexes:
        op.create_index("ix_evidence_files_job_id", "evidence_files", ["job_id"], unique=True)

    # Ensure old databases have the same immutable evidence guard as fresh ones.
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
    DROP TRIGGER IF EXISTS events_evidence_immutable ON events;
    CREATE TRIGGER events_evidence_immutable
      BEFORE UPDATE ON events FOR EACH ROW
      EXECUTE FUNCTION prevent_event_evidence_mutation();
    """)


def downgrade() -> None:
    raise RuntimeError("Production schema hardening is intentionally not downgraded")
