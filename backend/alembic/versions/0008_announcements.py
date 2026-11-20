"""announcements to students

Revision ID: 8a5b6c7d9e04
Revises: 7f4a5b6c8d93
Create Date: 2026-11-20 01:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '8a5b6c7d9e04'
down_revision: Union[str, None] = '7f4a5b6c8d93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'announcements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('applies_to_all', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('show_until', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_announcements_author_id', 'announcements', ['author_id'])
    op.create_index('ix_announcements_show_until', 'announcements', ['show_until'])
    op.create_table(
        'announcement_batches',
        sa.Column('announcement_id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['announcement_id'], ['announcements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('announcement_id', 'batch_id'),
    )
    op.execute('ALTER TABLE announcements ENABLE ROW LEVEL SECURITY')  # see 0005
    op.execute('ALTER TABLE announcement_batches ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table('announcement_batches')
    op.drop_index('ix_announcements_show_until', table_name='announcements')
    op.drop_index('ix_announcements_author_id', table_name='announcements')
    op.drop_table('announcements')
