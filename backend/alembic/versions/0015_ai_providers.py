"""ai providers: admin-managed AI provider keys (encrypted) and models

Revision ID: f5b2c3d4e671
Revises: e4a1b2c3d560
Create Date: 2026-11-23 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f5b2c3d4e671'
down_revision: Union[str, None] = 'e4a1b2c3d560'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ai_providers',
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('api_key_enc', sa.Text(), nullable=True),
        sa.Column('key_hint', sa.String(length=8), nullable=True),
        sa.Column('model', sa.String(length=120), nullable=True),
        sa.Column('base_url', sa.String(length=300), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('updated_by_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('provider'),
    )


def downgrade() -> None:
    op.drop_table('ai_providers')
