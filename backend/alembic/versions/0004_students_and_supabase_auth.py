"""students, batches, student attendance, Supabase Auth link

Revision ID: 4c1d2e3f5a60
Revises: 07a8f7ba0f96
Create Date: 2026-11-19 23:00:00

- roles: allow the new 'student' role and insert it
- users: auth_user_id (Supabase), student_code, batch_id, roll_number, phone, active_session_id/at
- batches, student_attendance
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '4c1d2e3f5a60'
down_revision: Union[str, None] = '07a8f7ba0f96'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES_OLD = "('admin', 'team_lead', 'artist')"
ROLES_NEW = "('admin', 'team_lead', 'artist', 'student')"


def _replace_role_check(values: str) -> None:
    """The role CHECK constraint was created by SQLAlchemy; find it by definition rather than by name."""
    op.execute("""
        DO $$
        DECLARE c record;
        BEGIN
          FOR c IN SELECT conname FROM pg_constraint
                   WHERE conrelid = 'roles'::regclass AND contype = 'c'
                     AND position('team_lead' in pg_get_constraintdef(oid)) > 0
          LOOP
            -- Written without percent signs: database drivers read them as parameter markers.
            EXECUTE 'ALTER TABLE roles DROP CONSTRAINT ' || quote_ident(c.conname);
          END LOOP;
        END $$;
    """)
    op.create_check_constraint("role_name", "roles", f"name IN {values}")


def upgrade() -> None:
    _replace_role_check(ROLES_NEW)
    op.execute("INSERT INTO roles (name, description) SELECT 'student', 'Marks their own daily attendance' "
               "WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'student')")

    op.create_table(
        'batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('teacher_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['teacher_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index('ix_batches_teacher_id', 'batches', ['teacher_id'])
    op.create_index('ix_batches_deleted_at', 'batches', ['deleted_at'])

    op.add_column('users', sa.Column('auth_user_id', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('student_code', sa.String(length=40), nullable=True))
    op.add_column('users', sa.Column('batch_id', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('roll_number', sa.String(length=40), nullable=True))
    op.add_column('users', sa.Column('phone', sa.String(length=32), nullable=True))
    op.add_column('users', sa.Column('active_session_id', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('active_session_at', sa.Integer(), nullable=True))
    op.create_index('ix_users_auth_user_id', 'users', ['auth_user_id'], unique=True)
    op.create_index('ix_users_student_code', 'users', ['student_code'], unique=True)
    op.create_index('ix_users_batch_id', 'users', ['batch_id'])
    op.create_foreign_key('fk_users_batch_id_batches', 'users', 'batches', ['batch_id'], ['id'], ondelete='SET NULL')

    op.create_table(
        'student_attendance',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('status', sa.Enum('present', 'absent', name='student_attendance_status', native_enum=False,
                                    create_constraint=True, length=40), nullable=False),
        sa.Column('marked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('corrected_by_id', sa.Integer(), nullable=True),
        sa.Column('corrected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['student_id'], ['users.id']),
        sa.ForeignKeyConstraint(['corrected_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('student_id', 'day', name='uq_student_attendance_student_day'),
    )
    op.create_index('ix_student_attendance_student_id', 'student_attendance', ['student_id'])
    op.create_index('ix_student_attendance_day', 'student_attendance', ['day'])


def downgrade() -> None:
    op.drop_index('ix_student_attendance_day', table_name='student_attendance')
    op.drop_index('ix_student_attendance_student_id', table_name='student_attendance')
    op.drop_table('student_attendance')
    op.drop_constraint('fk_users_batch_id_batches', 'users', type_='foreignkey')
    for ix in ('ix_users_batch_id', 'ix_users_student_code', 'ix_users_auth_user_id'):
        op.drop_index(ix, table_name='users')
    for col in ('active_session_at', 'active_session_id', 'phone', 'roll_number', 'batch_id', 'student_code',
                'auth_user_id'):
        op.drop_column('users', col)
    op.drop_index('ix_batches_deleted_at', table_name='batches')
    op.drop_index('ix_batches_teacher_id', table_name='batches')
    op.drop_table('batches')
    op.execute("DELETE FROM users WHERE role_id IN (SELECT id FROM roles WHERE name = 'student')")
    op.execute("DELETE FROM roles WHERE name = 'student'")
    _replace_role_check(ROLES_OLD)
