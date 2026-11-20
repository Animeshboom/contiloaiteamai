"""studio chat: messages and read markers

Revision ID: d3f0a1b2c459
Revises: c2e9f0a1b348
Create Date: 2026-11-20 06:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd3f0a1b2c459'
down_revision: Union[str, None] = 'c2e9f0a1b348'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel', sa.String(length=40), nullable=False),
        sa.Column('sender_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_chat_messages_channel_id', 'chat_messages', ['channel', 'id'])
    op.create_index('ix_chat_messages_sender_id', 'chat_messages', ['sender_id'])
    op.create_index('ix_chat_messages_created_at', 'chat_messages', ['created_at'])
    op.create_table(
        'chat_reads',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel', sa.String(length=40), nullable=False),
        sa.Column('last_read_id', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('user_id', 'channel'),
    )
    op.execute('ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY')  # see 0005
    op.execute('ALTER TABLE chat_reads ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table('chat_reads')
    op.drop_index('ix_chat_messages_created_at', table_name='chat_messages')
    op.drop_index('ix_chat_messages_sender_id', table_name='chat_messages')
    op.drop_index('ix_chat_messages_channel_id', table_name='chat_messages')
    op.drop_table('chat_messages')
