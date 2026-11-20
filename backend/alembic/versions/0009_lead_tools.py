"""team-lead tools: review rating, feedback phrases, weekly targets, reassigned slot status

Revision ID: 9b6c7d8e0f15
Revises: 8a5b6c7d9e04
Create Date: 2026-11-20 02:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '9b6c7d8e0f15'
down_revision: Union[str, None] = '8a5b6c7d9e04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUSES_OLD = "('assigned', 'in_progress', 'submitted', 'approved', 'revision_required', 'completed')"
STATUSES_NEW = "('assigned', 'in_progress', 'submitted', 'approved', 'revision_required', 'completed', 'reassigned')"
PHRASES = ["Fix lighting", "Check continuity", "Match the reference", "Clean up edges", "Timing feels off",
           "Great work"]


def _replace_status_check(table: str, name: str, values: str) -> None:
    """Drop the SQLAlchemy-made CHECK on ``status`` (found by definition), then add the new one.
    Written without percent signs: database drivers read them as parameter markers."""
    op.execute(f"""
        DO $$
        DECLARE c record;
        BEGIN
          FOR c IN SELECT conname FROM pg_constraint
                   WHERE conrelid = '{table}'::regclass AND contype = 'c'
                     AND position('revision_required' in pg_get_constraintdef(oid)) > 0
          LOOP
            EXECUTE 'ALTER TABLE {table} DROP CONSTRAINT ' || quote_ident(c.conname);
          END LOOP;
        END $$;
    """)
    op.create_check_constraint(name, table, f"status IN {values}")


def upgrade() -> None:
    _replace_status_check("assignments", "assignment_status", STATUSES_NEW)
    _replace_status_check("assignment_assignees", "assignee_status", STATUSES_NEW)
    op.add_column('reviews', sa.Column('rating', sa.Integer(), nullable=True))

    phrases = op.create_table(
        'feedback_phrases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('text', sa.String(length=200), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('text'),
    )
    op.bulk_insert(phrases, [{"text": t, "position": i} for i, t in enumerate(PHRASES)])

    op.create_table(
        'weekly_targets',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('scenes_per_week', sa.Integer(), nullable=False),
        sa.Column('set_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['set_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('user_id'),
    )
    op.execute('ALTER TABLE feedback_phrases ENABLE ROW LEVEL SECURITY')  # see 0005
    op.execute('ALTER TABLE weekly_targets ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table('weekly_targets')
    op.drop_table('feedback_phrases')
    op.drop_column('reviews', 'rating')
    op.execute("UPDATE assignment_assignees SET status = 'revision_required' WHERE status = 'reassigned'")
    _replace_status_check("assignment_assignees", "assignee_status", STATUSES_OLD)
    _replace_status_check("assignments", "assignment_status", STATUSES_OLD)
