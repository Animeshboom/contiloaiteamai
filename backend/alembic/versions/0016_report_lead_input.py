"""report lead input: team lead notes, tomorrow's plan, per-artist remarks and links on daily reports

Revision ID: a6c3d4e5f782
Revises: f5b2c3d4e671
Create Date: 2026-11-23 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a6c3d4e5f782'
down_revision: Union[str, None] = 'f5b2c3d4e671'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    op.add_column('daily_reports', sa.Column('lead_input', JSON, nullable=True))


def downgrade() -> None:
    op.drop_column('daily_reports', 'lead_input')
