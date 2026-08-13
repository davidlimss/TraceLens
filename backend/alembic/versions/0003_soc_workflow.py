"""add SOC finding workflow

Revision ID: 0003_soc_workflow
Revises: 0002_security_enrichment
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_soc_workflow"
down_revision = "0002_security_enrichment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("findings")}
    indexes = {item["name"] for item in inspector.get_indexes("findings")}
    for name, column in (
        ("workflow_status", sa.Column("workflow_status", sa.String(32), nullable=False, server_default="new")),
        ("disposition", sa.Column("disposition", sa.String(64), nullable=True)),
        ("assigned_to", sa.Column("assigned_to", sa.String(128), nullable=True)),
        ("analyst_notes", sa.Column("analyst_notes", sa.JSON(), nullable=False, server_default="[]")),
        ("workflow_updated_at", sa.Column("workflow_updated_at", sa.DateTime(timezone=True), nullable=True)),
    ):
        if name not in columns:
            op.add_column("findings", column)
    for name, column in (("ix_findings_workflow_status", "workflow_status"),
                         ("ix_findings_disposition", "disposition"),
                         ("ix_findings_assigned_to", "assigned_to")):
        if name not in indexes:
            op.create_index(name, "findings", [column])


def downgrade() -> None:
    op.drop_index("ix_findings_assigned_to", table_name="findings")
    op.drop_index("ix_findings_disposition", table_name="findings")
    op.drop_index("ix_findings_workflow_status", table_name="findings")
    op.drop_column("findings", "workflow_updated_at")
    op.drop_column("findings", "analyst_notes")
    op.drop_column("findings", "assigned_to")
    op.drop_column("findings", "disposition")
    op.drop_column("findings", "workflow_status")
