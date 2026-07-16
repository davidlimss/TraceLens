"""Security telemetry and finding enrichment.

Revision ID: 0002_security_enrichment
Revises: 0001_baseline
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_security_enrichment"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    event_columns = [
        ("event_code", sa.String(128)), ("command_line", sa.Text()),
        ("parent_process_name", sa.String(512)), ("source_port", sa.Integer()),
        ("destination_port", sa.Integer()), ("protocol", sa.String(32)),
        ("http_method", sa.String(16)), ("http_status", sa.Integer()),
        ("url_path", sa.Text()), ("user_agent", sa.Text()), ("file_hash", sa.String(128)),
    ]
    for name, column_type in event_columns:
        op.add_column("events", sa.Column(name, column_type, nullable=True))
    op.create_index("ix_events_event_code", "events", ["event_code"])
    op.create_index("ix_events_file_hash", "events", ["file_hash"])
    op.add_column("findings", sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.5"))
    op.add_column("findings", sa.Column("confidence_breakdown", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.add_column("findings", sa.Column("mitre_technique", sa.String(32), nullable=True))
    op.add_column("findings", sa.Column("mitre_tactic", sa.String(64), nullable=True))
    op.add_column("findings", sa.Column("false_positive_considerations", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    op.add_column("findings", sa.Column("recommended_queries", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    op.create_index("ix_findings_mitre_technique", "findings", ["mitre_technique"])


def downgrade() -> None:
    op.drop_index("ix_findings_mitre_technique", table_name="findings")
    for name in ("recommended_queries", "false_positive_considerations", "mitre_tactic",
                 "mitre_technique", "confidence_breakdown", "confidence_score"):
        op.drop_column("findings", name)
    op.drop_index("ix_events_file_hash", table_name="events")
    op.drop_index("ix_events_event_code", table_name="events")
    for name in ("file_hash", "user_agent", "url_path", "http_status", "http_method", "protocol",
                 "destination_port", "source_port", "parent_process_name", "command_line", "event_code"):
        op.drop_column("events", name)
