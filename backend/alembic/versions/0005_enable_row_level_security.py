"""enable row level security on every table

Revision ID: 5d2e3f4a6b71
Revises: 4c1d2e3f5a60
Create Date: 2026-11-19 23:30:00

On Supabase, every table in the public schema is reachable through the Data API with the public
(publishable) key. With RLS on and no policies, that API can read and write nothing. The StudioTrack API
connects as the table owner, which bypasses RLS, so the app itself is unaffected. On plain Postgres
(Docker, Neon) this is harmless for the same reason.
"""
from typing import Sequence, Union

from alembic import op

revision: str = '5d2e3f4a6b71'
down_revision: Union[str, None] = '4c1d2e3f5a60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = [
    "alembic_version", "roles", "teams", "users", "batches", "authorized_recipients", "projects", "episodes",
    "scenes", "assignments", "assignment_assignees", "assignment_scenes", "attendance", "student_attendance",
    "submissions", "submission_deliverables", "submission_attachments", "reviews", "notifications",
    "email_logs", "daily_reports", "audit_logs",
]


def upgrade() -> None:
    for t in TABLES:
        op.execute(f'ALTER TABLE IF EXISTS "{t}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    for t in TABLES:
        op.execute(f'ALTER TABLE IF EXISTS "{t}" DISABLE ROW LEVEL SECURITY')
