"""in-app day reports: lead sends to admin with issues; admin comments

Revision ID: b1d8e9f0a237
Revises: a0c7d8e9f126
Create Date: 2026-11-20 04:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b1d8e9f0a237'
down_revision: Union[str, None] = 'a0c7d8e9f126'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('daily_reports', sa.Column('auto_generated', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('daily_reports', sa.Column('issues', sa.Text(), nullable=True))
    op.add_column('daily_reports', sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('daily_reports', sa.Column('submitted_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    op.add_column('daily_reports', sa.Column('admin_comment', sa.Text(), nullable=True))
    op.add_column('daily_reports', sa.Column('admin_commented_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('daily_reports', sa.Column('admin_commented_by_id', sa.Integer(), sa.ForeignKey('users.id'),
                                             nullable=True))


def downgrade() -> None:
    for col in ('admin_commented_by_id', 'admin_commented_at', 'admin_comment', 'submitted_by_id', 'submitted_at',
                'issues', 'auto_generated'):
        op.drop_column('daily_reports', col)
