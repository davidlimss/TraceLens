"""TraceLens schema baseline.

Revision ID: 0001_baseline
Revises: None
"""
from alembic import op

from app.database import Base
import app.models  # noqa: F401

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Safe for both a fresh database and the pre-Alembic MVP database.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("Baseline downgrade is intentionally disabled to protect forensic data")
