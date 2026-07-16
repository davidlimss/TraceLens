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
    op.add_column("findings", sa.Column("workflow_status", sa.String(32), nullable=False, server_default="new"))
    op.add_column("findings", sa.Column("disposition", sa.String(64), nullable=True))
    op.add_column("findings", sa.Column("assigned_to", sa.String(128), nullable=True))
    op.add_column("findings", sa.Column("analyst_notes", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("findings", sa.Column("workflow_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_findings_workflow_status", "findings", ["workflow_status"])
    op.create_index("ix_findings_disposition", "findings", ["disposition"])
    op.create_index("ix_findings_assigned_to", "findings", ["assigned_to"])


def downgrade() -> None:
    op.drop_index("ix_findings_assigned_to", table_name="findings")
    op.drop_index("ix_findings_disposition", table_name="findings")
    op.drop_index("ix_findings_workflow_status", table_name="findings")
    op.drop_column("findings", "workflow_updated_at")
    op.drop_column("findings", "analyst_notes")
    op.drop_column("findings", "assigned_to")
    op.drop_column("findings", "disposition")
    op.drop_column("findings", "workflow_status")
