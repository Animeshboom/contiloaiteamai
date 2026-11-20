"""student leave requests

Revision ID: 7f4a5b6c8d93
Revises: 6e3f4a5b7c82
Create Date: 2026-11-20 00:30:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '7f4a5b6c8d93'
down_revision: Union[str, None] = '6e3f4a5b7c82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'leave_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('start_day', sa.Date(), nullable=False),
        sa.Column('end_day', sa.Date(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('pending', 'approved', 'rejected', 'cancelled', name='leave_status',
                                    native_enum=False, create_constraint=True, length=40), nullable=False),
        sa.Column('decided_by_id', sa.Integer(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decision_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['student_id'], ['users.id']),
        sa.ForeignKeyConstraint(['decided_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ('student_id', 'start_day', 'end_day', 'status'):
        op.create_index(f'ix_leave_requests_{col}', 'leave_requests', [col])
    op.execute('ALTER TABLE leave_requests ENABLE ROW LEVEL SECURITY')  # see 0005


def downgrade() -> None:
    for col in ('status', 'end_day', 'start_day', 'student_id'):
        op.drop_index(f'ix_leave_requests_{col}', table_name='leave_requests')
    op.drop_table('leave_requests')
