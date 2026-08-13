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
    inspector = sa.inspect(op.get_bind())
    existing_event_columns = {item["name"] for item in inspector.get_columns("events")}
    existing_finding_columns = {item["name"] for item in inspector.get_columns("findings")}
    event_indexes = {item["name"] for item in inspector.get_indexes("events")}
    finding_indexes = {item["name"] for item in inspector.get_indexes("findings")}
    event_columns = [
        ("event_code", sa.String(128)), ("command_line", sa.Text()),
        ("parent_process_name", sa.String(512)), ("source_port", sa.Integer()),
        ("destination_port", sa.Integer()), ("protocol", sa.String(32)),
        ("http_method", sa.String(16)), ("http_status", sa.Integer()),
        ("url_path", sa.Text()), ("user_agent", sa.Text()), ("file_hash", sa.String(128)),
    ]
    for name, column_type in event_columns:
        if name not in existing_event_columns:
            op.add_column("events", sa.Column(name, column_type, nullable=True))
    if "ix_events_event_code" not in event_indexes:
        op.create_index("ix_events_event_code", "events", ["event_code"])
    if "ix_events_file_hash" not in event_indexes:
        op.create_index("ix_events_file_hash", "events", ["file_hash"])
    finding_columns = [
        ("confidence_score", sa.Float(), False, "0.5"),
        ("confidence_breakdown", sa.JSON(), False, sa.text("'{}'::json")),
        ("mitre_technique", sa.String(32), True, None),
        ("mitre_tactic", sa.String(64), True, None),
        ("false_positive_considerations", sa.JSON(), False, sa.text("'[]'::json")),
        ("recommended_queries", sa.JSON(), False, sa.text("'[]'::json")),
    ]
    for name, column_type, nullable, default in finding_columns:
        if name not in existing_finding_columns:
            kwargs = {"nullable": nullable}
            if default is not None:
                kwargs["server_default"] = default
            op.add_column("findings", sa.Column(name, column_type, **kwargs))
    if "ix_findings_mitre_technique" not in finding_indexes:
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
