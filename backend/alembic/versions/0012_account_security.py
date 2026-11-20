"""account security: lockout, admin two-step login, known admin devices

Revision ID: c2e9f0a1b348
Revises: b1d8e9f0a237
Create Date: 2026-11-20 05:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c2e9f0a1b348'
down_revision: Union[str, None] = 'b1d8e9f0a237'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('failed_logins', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('totp_secret', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('totp_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        'known_devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('user_agent', sa.String(length=300), nullable=True),
        sa.Column('ip', sa.String(length=64), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_known_devices_user_id', 'known_devices', ['user_id'])
    op.execute('ALTER TABLE known_devices ENABLE ROW LEVEL SECURITY')  # see 0005


def downgrade() -> None:
    op.drop_index('ix_known_devices_user_id', table_name='known_devices')
    op.drop_table('known_devices')
    for col in ('totp_enabled', 'totp_secret', 'locked_until', 'failed_logins'):
        op.drop_column('users', col)
