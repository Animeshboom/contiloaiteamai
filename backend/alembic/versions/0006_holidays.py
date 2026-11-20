"""holidays (for everyone or chosen batches)

Revision ID: 6e3f4a5b7c82
Revises: 5d2e3f4a6b71
Create Date: 2026-11-20 00:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '6e3f4a5b7c82'
down_revision: Union[str, None] = '5d2e3f4a6b71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'holidays',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('applies_to_all', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_holidays_day', 'holidays', ['day'])
    op.create_table(
        'holiday_batches',
        sa.Column('holiday_id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['holiday_id'], ['holidays.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('holiday_id', 'batch_id'),
    )
    # Same reason as 0005: keep Supabase's public Data API away from these tables.
    op.execute('ALTER TABLE holidays ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE holiday_batches ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table('holiday_batches')
    op.drop_index('ix_holidays_day', table_name='holidays')
    op.drop_table('holidays')
