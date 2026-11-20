"""merge students into artists: three roles only (admin, team lead, artist)

Revision ID: a0c7d8e9f126
Revises: 9b6c7d8e0f15
Create Date: 2026-11-20 03:00:00

- every student account becomes an artist (same account, password and work history)
- users.student_code -> users.employee_code (sign-in ID); batch_id and roll_number dropped
- batches, student_attendance dropped (artists use check-in/out)
- holidays and announcements target teams instead of batches
- leave_requests.student_id -> user_id (leave for everyone)
- attendance.work_note: what the artist did today / blockers (written at check-out)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a0c7d8e9f126'
down_revision: Union[str, None] = '9b6c7d8e0f15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _replace_role_check(values: str) -> None:
    op.execute("""
        DO $$
        DECLARE c record;
        BEGIN
          FOR c IN SELECT conname FROM pg_constraint
                   WHERE conrelid = 'roles'::regclass AND contype = 'c'
                     AND position('team_lead' in pg_get_constraintdef(oid)) > 0
          LOOP
            EXECUTE 'ALTER TABLE roles DROP CONSTRAINT ' || quote_ident(c.conname);
          END LOOP;
        END $$;
    """)
    op.create_check_constraint("role_name", "roles", f"name IN {values}")


def upgrade() -> None:
    # 1. students become artists (same row: id, password, assignments, submissions all stay)
    op.execute("""
        UPDATE users SET role_id = (SELECT id FROM roles WHERE name = 'artist'),
                         job_title = COALESCE(job_title, 'Artist')
        WHERE role_id = (SELECT id FROM roles WHERE name = 'student')
    """)
    op.execute("DELETE FROM roles WHERE name = 'student'")
    _replace_role_check("('admin', 'team_lead', 'artist')")

    # 2. sign-in ID; batches go away
    op.alter_column('users', 'student_code', new_column_name='employee_code')
    op.execute('ALTER INDEX IF EXISTS ix_users_student_code RENAME TO ix_users_employee_code')
    op.drop_constraint('fk_users_batch_id_batches', 'users', type_='foreignkey')
    op.drop_index('ix_users_batch_id', table_name='users')
    op.drop_column('users', 'batch_id')
    op.drop_column('users', 'roll_number')

    # 3. holidays / announcements: teams instead of batches
    op.drop_table('holiday_batches')
    op.create_table(
        'holiday_teams',
        sa.Column('holiday_id', sa.Integer(), sa.ForeignKey('holidays.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id', ondelete='CASCADE'), primary_key=True),
    )
    op.drop_table('announcement_batches')
    op.create_table(
        'announcement_teams',
        sa.Column('announcement_id', sa.Integer(), sa.ForeignKey('announcements.id', ondelete='CASCADE'),
                  primary_key=True),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id', ondelete='CASCADE'), primary_key=True),
    )
    # A batch-only holiday or announcement has lost its audience; make it studio-wide so nothing is hidden.
    op.execute("UPDATE holidays SET applies_to_all = true")
    op.execute("UPDATE announcements SET applies_to_all = true")

    # 4. student attendance and batches are gone
    op.drop_table('student_attendance')
    op.drop_table('batches')

    # 5. leave for everyone
    op.alter_column('leave_requests', 'student_id', new_column_name='user_id')
    op.execute('ALTER INDEX IF EXISTS ix_leave_requests_student_id RENAME TO ix_leave_requests_user_id')

    # 6. artist's end-of-day note
    op.add_column('attendance', sa.Column('work_note', sa.Text(), nullable=True))

    op.execute('ALTER TABLE holiday_teams ENABLE ROW LEVEL SECURITY')  # see 0005
    op.execute('ALTER TABLE announcement_teams ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    raise NotImplementedError("Students were merged into artists; this cannot be undone automatically. "
                              "Restore the database from a backup taken before upgrading.")
