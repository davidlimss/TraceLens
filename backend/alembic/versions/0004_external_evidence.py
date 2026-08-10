"""add immutable external evidence snapshots

Revision ID: 0004_external_evidence
Revises: 0003_soc_workflow
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_external_evidence"
down_revision = "0003_soc_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 uses metadata.create_all for a safe legacy bootstrap.  On a fresh
    # database that bootstrap already creates this table because the model is
    # imported by Alembic.  Keep this revision idempotent for that path.
    if "external_evidence" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "external_evidence",
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.case_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("external_event_id", sa.String(512), nullable=False),
        sa.Column("timestamp_original", sa.String(255), nullable=True),
        sa.Column("timestamp_normalized", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_log", sa.Text(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("query_sha256", sa.String(64), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_ip", sa.String(255), nullable=True),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("host", sa.String(255), nullable=True),
        sa.Column("event_action", sa.String(128), nullable=True),
        sa.Column("event_outcome", sa.String(32), nullable=True),
        sa.Column("severity", sa.String(32), nullable=False, server_default="info"),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.UniqueConstraint("case_id", "provider", "external_event_id", "content_sha256", name="uq_external_evidence_snapshot"),
    )
    op.create_index("ix_external_evidence_case_id", "external_evidence", ["case_id"])
    op.create_index("ix_external_evidence_provider", "external_evidence", ["provider"])
    op.create_index("ix_external_evidence_timestamp_normalized", "external_evidence", ["timestamp_normalized"])
    op.create_index("ix_external_evidence_content_sha256", "external_evidence", ["content_sha256"])
    op.create_index("ix_external_evidence_query_sha256", "external_evidence", ["query_sha256"])
    op.create_index("ix_external_evidence_source_ip", "external_evidence", ["source_ip"])
    op.create_index("ix_external_evidence_username", "external_evidence", ["username"])
    op.create_index("ix_external_evidence_host", "external_evidence", ["host"])
    op.execute("""
    CREATE OR REPLACE FUNCTION prevent_external_evidence_mutation() RETURNS trigger AS $$
    BEGIN
      IF NEW.raw_log IS DISTINCT FROM OLD.raw_log
         OR NEW.raw_payload IS DISTINCT FROM OLD.raw_payload
         OR NEW.content_sha256 IS DISTINCT FROM OLD.content_sha256
         OR NEW.provider IS DISTINCT FROM OLD.provider
         OR NEW.external_event_id IS DISTINCT FROM OLD.external_event_id THEN
        RAISE EXCEPTION 'external evidence fields are immutable';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER external_evidence_immutable
      BEFORE UPDATE ON external_evidence FOR EACH ROW
      EXECUTE FUNCTION prevent_external_evidence_mutation();
    """)


def downgrade() -> None:
    raise RuntimeError("External evidence is chain-of-custody data; downgrade is intentionally disabled")
