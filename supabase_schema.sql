BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 3e6f6404fdc8

CREATE TABLE authorized_recipients (
    id SERIAL NOT NULL, 
    email VARCHAR(255) NOT NULL, 
    name VARCHAR(160) NOT NULL, 
    purpose VARCHAR(40) NOT NULL, 
    is_active BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (email)
);

CREATE TABLE roles (
    id SERIAL NOT NULL, 
    name VARCHAR(40) NOT NULL, 
    description VARCHAR(255), 
    PRIMARY KEY (id), 
    UNIQUE (name), 
    CONSTRAINT role_name CHECK (name IN ('admin', 'team_lead', 'artist'))
);

CREATE TABLE teams (
    id SERIAL NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    department VARCHAR(120), 
    description TEXT, 
    lead_id INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    UNIQUE (name)
);

CREATE INDEX ix_teams_deleted_at ON teams (deleted_at);

CREATE INDEX ix_teams_lead_id ON teams (lead_id);

CREATE TABLE users (
    id SERIAL NOT NULL, 
    email VARCHAR(255) NOT NULL, 
    full_name VARCHAR(160) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    role_id INTEGER NOT NULL, 
    team_id INTEGER, 
    job_title VARCHAR(120), 
    is_active BOOLEAN NOT NULL, 
    token_version INTEGER NOT NULL, 
    last_login_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(role_id) REFERENCES roles (id), 
    FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE SET NULL
);

CREATE INDEX ix_users_deleted_at ON users (deleted_at);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE INDEX ix_users_role_id ON users (role_id);

CREATE INDEX ix_users_team_id ON users (team_id);

ALTER TABLE teams ADD CONSTRAINT fk_teams_lead_id_users FOREIGN KEY(lead_id) REFERENCES users (id) ON DELETE SET NULL;

CREATE TABLE attendance (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    work_date DATE NOT NULL, 
    check_in_at TIMESTAMP WITH TIME ZONE, 
    check_out_at TIMESTAMP WITH TIME ZONE, 
    status VARCHAR(40) NOT NULL, 
    notes TEXT, 
    corrected_by_id INTEGER, 
    corrected_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(corrected_by_id) REFERENCES users (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    CONSTRAINT uq_attendance_user_date UNIQUE (user_id, work_date), 
    CONSTRAINT attendance_status CHECK (status IN ('present', 'absent', 'half_day', 'leave'))
);

CREATE INDEX ix_attendance_user_id ON attendance (user_id);

CREATE INDEX ix_attendance_work_date ON attendance (work_date);

CREATE TABLE audit_logs (
    id SERIAL NOT NULL, 
    actor_id INTEGER, 
    action VARCHAR(80) NOT NULL, 
    entity_type VARCHAR(60) NOT NULL, 
    entity_id INTEGER, 
    before JSONB, 
    after JSONB, 
    ip_address VARCHAR(64), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE INDEX ix_audit_entity ON audit_logs (entity_type, entity_id);

CREATE INDEX ix_audit_logs_action ON audit_logs (action);

CREATE INDEX ix_audit_logs_actor_id ON audit_logs (actor_id);

CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);

CREATE TABLE daily_reports (
    id SERIAL NOT NULL, 
    report_date DATE NOT NULL, 
    team_id INTEGER, 
    filters JSONB NOT NULL, 
    metrics JSONB NOT NULL, 
    ai_summary TEXT, 
    ai_generated BOOLEAN NOT NULL, 
    subject VARCHAR(300) NOT NULL, 
    body TEXT NOT NULL, 
    status VARCHAR(40) NOT NULL, 
    recipients JSONB NOT NULL, 
    created_by_id INTEGER NOT NULL, 
    approved_by_id INTEGER, 
    approved_at TIMESTAMP WITH TIME ZONE, 
    sent_by_id INTEGER, 
    sent_at TIMESTAMP WITH TIME ZONE, 
    delivery_status VARCHAR(40), 
    gmail_message_id VARCHAR(200), 
    gmail_draft_id VARCHAR(200), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(approved_by_id) REFERENCES users (id), 
    FOREIGN KEY(created_by_id) REFERENCES users (id), 
    FOREIGN KEY(sent_by_id) REFERENCES users (id), 
    FOREIGN KEY(team_id) REFERENCES teams (id), 
    CONSTRAINT report_status CHECK (status IN ('draft', 'approved', 'sent', 'failed'))
);

CREATE INDEX ix_daily_reports_date_status ON daily_reports (report_date, status);

CREATE TABLE email_logs (
    id SERIAL NOT NULL, 
    idempotency_key VARCHAR(200) NOT NULL, 
    tool_name VARCHAR(80) NOT NULL, 
    provider VARCHAR(40) NOT NULL, 
    recipients JSONB NOT NULL, 
    subject VARCHAR(300) NOT NULL, 
    body_preview TEXT, 
    status VARCHAR(40) NOT NULL, 
    provider_message_id VARCHAR(200), 
    error TEXT, 
    attempts INTEGER NOT NULL, 
    entity_type VARCHAR(60), 
    entity_id INTEGER, 
    triggered_by_id INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(triggered_by_id) REFERENCES users (id), 
    UNIQUE (idempotency_key), 
    CONSTRAINT email_status CHECK (status IN ('pending', 'sent', 'drafted', 'failed', 'blocked'))
);

CREATE INDEX ix_email_logs_status ON email_logs (status);

CREATE TABLE notifications (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    event_type VARCHAR(60) NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    message TEXT NOT NULL, 
    link VARCHAR(255), 
    entity_type VARCHAR(60), 
    entity_id INTEGER, 
    dedupe_key VARCHAR(200) NOT NULL, 
    read_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    UNIQUE (dedupe_key)
);

CREATE INDEX ix_notifications_user_id ON notifications (user_id);

CREATE INDEX ix_notifications_user_unread ON notifications (user_id, read_at);

CREATE TABLE projects (
    id SERIAL NOT NULL, 
    code VARCHAR(32) NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    description TEXT, 
    project_type VARCHAR(40) NOT NULL, 
    status VARCHAR(40) NOT NULL, 
    start_date DATE, 
    expected_completion_date DATE, 
    team_id INTEGER, 
    created_by_id INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
    FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE SET NULL, 
    UNIQUE (code), 
    CONSTRAINT project_type CHECK (project_type IN ('feature_film', 'series', 'short_film', 'commercial', 'music_video', 'other')), 
    CONSTRAINT project_status CHECK (status IN ('planning', 'active', 'on_hold', 'completed', 'archived'))
);

CREATE INDEX ix_projects_deleted_at ON projects (deleted_at);

CREATE INDEX ix_projects_status ON projects (status);

CREATE INDEX ix_projects_team_id ON projects (team_id);

CREATE INDEX ix_projects_title ON projects (title);

CREATE TABLE episodes (
    id SERIAL NOT NULL, 
    project_id INTEGER NOT NULL, 
    episode_number INTEGER NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    description TEXT, 
    status VARCHAR(40) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
    CONSTRAINT uq_episode_project_number UNIQUE (project_id, episode_number), 
    CONSTRAINT episode_status CHECK (status IN ('not_started', 'in_progress', 'in_review', 'approved', 'completed'))
);

CREATE INDEX ix_episodes_deleted_at ON episodes (deleted_at);

CREATE INDEX ix_episodes_project_id ON episodes (project_id);

CREATE TABLE assignments (
    id SERIAL NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    project_id INTEGER NOT NULL, 
    episode_id INTEGER, 
    description TEXT, 
    expected_deliverables TEXT, 
    assignment_date DATE NOT NULL, 
    deadline TIMESTAMP WITH TIME ZONE NOT NULL, 
    priority VARCHAR(40) NOT NULL, 
    status VARCHAR(40) NOT NULL, 
    created_by_id INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(created_by_id) REFERENCES users (id), 
    FOREIGN KEY(episode_id) REFERENCES episodes (id), 
    FOREIGN KEY(project_id) REFERENCES projects (id), 
    CONSTRAINT priority CHECK (priority IN ('low', 'medium', 'high', 'urgent')), 
    CONSTRAINT assignment_status CHECK (status IN ('assigned', 'in_progress', 'submitted', 'approved', 'revision_required', 'completed'))
);

CREATE INDEX ix_assignments_assignment_date ON assignments (assignment_date);

CREATE INDEX ix_assignments_created_by_id ON assignments (created_by_id);

CREATE INDEX ix_assignments_deadline_status ON assignments (deadline, status);

CREATE INDEX ix_assignments_deleted_at ON assignments (deleted_at);

CREATE INDEX ix_assignments_episode_id ON assignments (episode_id);

CREATE INDEX ix_assignments_project_id ON assignments (project_id);

CREATE TABLE scenes (
    id SERIAL NOT NULL, 
    episode_id INTEGER NOT NULL, 
    scene_number INTEGER NOT NULL, 
    title VARCHAR(200), 
    description TEXT, 
    status VARCHAR(40) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(episode_id) REFERENCES episodes (id) ON DELETE CASCADE, 
    CONSTRAINT uq_scene_episode_number UNIQUE (episode_id, scene_number), 
    CONSTRAINT scene_status CHECK (status IN ('not_started', 'in_progress', 'in_review', 'approved', 'completed'))
);

CREATE INDEX ix_scenes_deleted_at ON scenes (deleted_at);

CREATE INDEX ix_scenes_episode_id ON scenes (episode_id);

CREATE TABLE assignment_assignees (
    id SERIAL NOT NULL, 
    assignment_id INTEGER NOT NULL, 
    user_id INTEGER NOT NULL, 
    status VARCHAR(40) NOT NULL, 
    reported_progress_pct INTEGER NOT NULL, 
    progress_note TEXT, 
    started_at TIMESTAMP WITH TIME ZONE, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(assignment_id) REFERENCES assignments (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    CONSTRAINT uq_assignment_assignee UNIQUE (assignment_id, user_id), 
    CONSTRAINT assignee_status CHECK (status IN ('assigned', 'in_progress', 'submitted', 'approved', 'revision_required', 'completed'))
);

CREATE INDEX ix_assignment_assignees_assignment_id ON assignment_assignees (assignment_id);

CREATE INDEX ix_assignment_assignees_status ON assignment_assignees (status);

CREATE INDEX ix_assignment_assignees_user_id ON assignment_assignees (user_id);

CREATE TABLE assignment_scenes (
    id SERIAL NOT NULL, 
    assignment_id INTEGER NOT NULL, 
    scene_id INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(assignment_id) REFERENCES assignments (id) ON DELETE CASCADE, 
    FOREIGN KEY(scene_id) REFERENCES scenes (id), 
    CONSTRAINT uq_assignment_scene UNIQUE (assignment_id, scene_id)
);

CREATE INDEX ix_assignment_scenes_assignment_id ON assignment_scenes (assignment_id);

CREATE INDEX ix_assignment_scenes_scene_id ON assignment_scenes (scene_id);

CREATE TABLE submissions (
    id SERIAL NOT NULL, 
    assignment_id INTEGER NOT NULL, 
    assignee_id INTEGER NOT NULL, 
    artist_id INTEGER NOT NULL, 
    revision_number INTEGER NOT NULL, 
    previous_submission_id INTEGER, 
    submitted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    submission_date DATE NOT NULL, 
    scenes_completed_count INTEGER NOT NULL, 
    work_description TEXT NOT NULL, 
    output_links JSONB NOT NULL, 
    comments TEXT, 
    status VARCHAR(40) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(artist_id) REFERENCES users (id), 
    FOREIGN KEY(assignee_id) REFERENCES assignment_assignees (id), 
    FOREIGN KEY(assignment_id) REFERENCES assignments (id), 
    FOREIGN KEY(previous_submission_id) REFERENCES submissions (id), 
    CONSTRAINT uq_submission_assignee_revision UNIQUE (assignee_id, revision_number), 
    CONSTRAINT submission_status CHECK (status IN ('pending_review', 'approved', 'rejected'))
);

CREATE INDEX ix_submissions_artist_id ON submissions (artist_id);

CREATE INDEX ix_submissions_assignee_id ON submissions (assignee_id);

CREATE INDEX ix_submissions_assignment_id ON submissions (assignment_id);

CREATE INDEX ix_submissions_status ON submissions (status);

CREATE INDEX ix_submissions_submission_date ON submissions (submission_date);

CREATE INDEX ix_submissions_submitted_at ON submissions (submitted_at);

CREATE TABLE reviews (
    id SERIAL NOT NULL, 
    submission_id INTEGER NOT NULL, 
    reviewer_id INTEGER NOT NULL, 
    decision VARCHAR(40) NOT NULL, 
    feedback TEXT, 
    approved_scene_ids JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(reviewer_id) REFERENCES users (id), 
    FOREIGN KEY(submission_id) REFERENCES submissions (id), 
    CONSTRAINT review_decision CHECK (decision IN ('approved', 'rejected'))
);

CREATE INDEX ix_reviews_created_at ON reviews (created_at);

CREATE INDEX ix_reviews_reviewer_id ON reviews (reviewer_id);

CREATE INDEX ix_reviews_submission_id ON reviews (submission_id);

CREATE TABLE submission_attachments (
    id SERIAL NOT NULL, 
    submission_id INTEGER NOT NULL, 
    original_filename VARCHAR(255) NOT NULL, 
    stored_filename VARCHAR(255) NOT NULL, 
    content_type VARCHAR(120), 
    size_bytes BIGINT NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(submission_id) REFERENCES submissions (id) ON DELETE CASCADE, 
    UNIQUE (stored_filename)
);

CREATE INDEX ix_submission_attachments_submission_id ON submission_attachments (submission_id);

CREATE TABLE submission_deliverables (
    id SERIAL NOT NULL, 
    submission_id INTEGER NOT NULL, 
    scene_id INTEGER, 
    label VARCHAR(200) NOT NULL, 
    status VARCHAR(40) NOT NULL, 
    approved_by_id INTEGER, 
    approved_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(approved_by_id) REFERENCES users (id), 
    FOREIGN KEY(scene_id) REFERENCES scenes (id), 
    FOREIGN KEY(submission_id) REFERENCES submissions (id) ON DELETE CASCADE, 
    CONSTRAINT uq_deliverable_submission_scene UNIQUE (submission_id, scene_id), 
    CONSTRAINT deliverable_status CHECK (status IN ('submitted', 'approved', 'rejected'))
);

CREATE INDEX ix_submission_deliverables_scene_id ON submission_deliverables (scene_id);

CREATE INDEX ix_submission_deliverables_status ON submission_deliverables (status);

CREATE INDEX ix_submission_deliverables_submission_id ON submission_deliverables (submission_id);

INSERT INTO alembic_version (version_num) VALUES ('3e6f6404fdc8') RETURNING alembic_version.version_num;

-- Running upgrade 3e6f6404fdc8 -> 2f8ed47f668d

ALTER TABLE email_logs ADD COLUMN payload JSONB DEFAULT '{}' NOT NULL;

ALTER TABLE email_logs ADD COLUMN next_attempt_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE email_logs ADD COLUMN last_attempt_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE email_logs ADD COLUMN sent_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX ix_email_logs_next_attempt_at ON email_logs (next_attempt_at);

UPDATE alembic_version SET version_num='2f8ed47f668d' WHERE alembic_version.version_num = '3e6f6404fdc8';

-- Running upgrade 2f8ed47f668d -> 07a8f7ba0f96

ALTER TABLE daily_reports ADD COLUMN narrative JSONB DEFAULT '{}' NOT NULL;

ALTER TABLE daily_reports ADD COLUMN ai_status VARCHAR(40);

ALTER TABLE daily_reports ADD COLUMN ai_note TEXT;

ALTER TABLE daily_reports ADD COLUMN approval_token VARCHAR(64);

UPDATE alembic_version SET version_num='07a8f7ba0f96' WHERE alembic_version.version_num = '2f8ed47f668d';

-- Running upgrade 07a8f7ba0f96 -> 4c1d2e3f5a60

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
        END $$;;

ALTER TABLE roles ADD CONSTRAINT role_name CHECK (name IN ('admin', 'team_lead', 'artist', 'student'));

INSERT INTO roles (name, description) SELECT 'student', 'Marks their own daily attendance' WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'student');

CREATE TABLE batches (
    id SERIAL NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    description TEXT, 
    teacher_id INTEGER, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(teacher_id) REFERENCES users (id) ON DELETE SET NULL, 
    UNIQUE (name)
);

CREATE INDEX ix_batches_teacher_id ON batches (teacher_id);

CREATE INDEX ix_batches_deleted_at ON batches (deleted_at);

ALTER TABLE users ADD COLUMN auth_user_id VARCHAR(64);

ALTER TABLE users ADD COLUMN student_code VARCHAR(40);

ALTER TABLE users ADD COLUMN batch_id INTEGER;

ALTER TABLE users ADD COLUMN roll_number VARCHAR(40);

ALTER TABLE users ADD COLUMN phone VARCHAR(32);

ALTER TABLE users ADD COLUMN active_session_id VARCHAR(64);

ALTER TABLE users ADD COLUMN active_session_at INTEGER;

CREATE UNIQUE INDEX ix_users_auth_user_id ON users (auth_user_id);

CREATE UNIQUE INDEX ix_users_student_code ON users (student_code);

CREATE INDEX ix_users_batch_id ON users (batch_id);

ALTER TABLE users ADD CONSTRAINT fk_users_batch_id_batches FOREIGN KEY(batch_id) REFERENCES batches (id) ON DELETE SET NULL;

CREATE TABLE student_attendance (
    id SERIAL NOT NULL, 
    student_id INTEGER NOT NULL, 
    day DATE NOT NULL, 
    status VARCHAR(40) NOT NULL, 
    marked_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    reason TEXT, 
    corrected_by_id INTEGER, 
    corrected_at TIMESTAMP WITH TIME ZONE, 
    note TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(student_id) REFERENCES users (id), 
    FOREIGN KEY(corrected_by_id) REFERENCES users (id), 
    CONSTRAINT uq_student_attendance_student_day UNIQUE (student_id, day), 
    CONSTRAINT student_attendance_status CHECK (status IN ('present', 'absent'))
);

CREATE INDEX ix_student_attendance_student_id ON student_attendance (student_id);

CREATE INDEX ix_student_attendance_day ON student_attendance (day);

UPDATE alembic_version SET version_num='4c1d2e3f5a60' WHERE alembic_version.version_num = '07a8f7ba0f96';

-- Running upgrade 4c1d2e3f5a60 -> 5d2e3f4a6b71

ALTER TABLE IF EXISTS "alembic_version" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "roles" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "teams" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "users" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "batches" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "authorized_recipients" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "projects" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "episodes" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "scenes" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "assignments" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "assignment_assignees" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "assignment_scenes" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "attendance" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "student_attendance" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "submissions" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "submission_deliverables" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "submission_attachments" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "reviews" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "notifications" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "email_logs" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "daily_reports" ENABLE ROW LEVEL SECURITY;

ALTER TABLE IF EXISTS "audit_logs" ENABLE ROW LEVEL SECURITY;

UPDATE alembic_version SET version_num='5d2e3f4a6b71' WHERE alembic_version.version_num = '4c1d2e3f5a60';

-- Running upgrade 5d2e3f4a6b71 -> 6e3f4a5b7c82

CREATE TABLE holidays (
    id SERIAL NOT NULL, 
    day DATE NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    applies_to_all BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_holidays_day ON holidays (day);

CREATE TABLE holiday_batches (
    holiday_id INTEGER NOT NULL, 
    batch_id INTEGER NOT NULL, 
    PRIMARY KEY (holiday_id, batch_id), 
    FOREIGN KEY(holiday_id) REFERENCES holidays (id) ON DELETE CASCADE, 
    FOREIGN KEY(batch_id) REFERENCES batches (id) ON DELETE CASCADE
);

ALTER TABLE holidays ENABLE ROW LEVEL SECURITY;

ALTER TABLE holiday_batches ENABLE ROW LEVEL SECURITY;

UPDATE alembic_version SET version_num='6e3f4a5b7c82' WHERE alembic_version.version_num = '5d2e3f4a6b71';

-- Running upgrade 6e3f4a5b7c82 -> 7f4a5b6c8d93

CREATE TABLE leave_requests (
    id SERIAL NOT NULL, 
    student_id INTEGER NOT NULL, 
    start_day DATE NOT NULL, 
    end_day DATE NOT NULL, 
    reason TEXT NOT NULL, 
    status VARCHAR(40) NOT NULL, 
    decided_by_id INTEGER, 
    decided_at TIMESTAMP WITH TIME ZONE, 
    decision_note TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(student_id) REFERENCES users (id), 
    FOREIGN KEY(decided_by_id) REFERENCES users (id), 
    CONSTRAINT leave_status CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled'))
);

CREATE INDEX ix_leave_requests_student_id ON leave_requests (student_id);

CREATE INDEX ix_leave_requests_start_day ON leave_requests (start_day);

CREATE INDEX ix_leave_requests_end_day ON leave_requests (end_day);

CREATE INDEX ix_leave_requests_status ON leave_requests (status);

ALTER TABLE leave_requests ENABLE ROW LEVEL SECURITY;

UPDATE alembic_version SET version_num='7f4a5b6c8d93' WHERE alembic_version.version_num = '6e3f4a5b7c82';

-- Running upgrade 7f4a5b6c8d93 -> 8a5b6c7d9e04

CREATE TABLE announcements (
    id SERIAL NOT NULL, 
    title VARCHAR(160) NOT NULL, 
    body TEXT NOT NULL, 
    author_id INTEGER, 
    applies_to_all BOOLEAN DEFAULT true NOT NULL, 
    show_until DATE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(author_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_announcements_author_id ON announcements (author_id);

CREATE INDEX ix_announcements_show_until ON announcements (show_until);

CREATE TABLE announcement_batches (
    announcement_id INTEGER NOT NULL, 
    batch_id INTEGER NOT NULL, 
    PRIMARY KEY (announcement_id, batch_id), 
    FOREIGN KEY(announcement_id) REFERENCES announcements (id) ON DELETE CASCADE, 
    FOREIGN KEY(batch_id) REFERENCES batches (id) ON DELETE CASCADE
);

ALTER TABLE announcements ENABLE ROW LEVEL SECURITY;

ALTER TABLE announcement_batches ENABLE ROW LEVEL SECURITY;

UPDATE alembic_version SET version_num='8a5b6c7d9e04' WHERE alembic_version.version_num = '7f4a5b6c8d93';

-- Running upgrade 8a5b6c7d9e04 -> 9b6c7d8e0f15

DO $$
        DECLARE c record;
        BEGIN
          FOR c IN SELECT conname FROM pg_constraint
                   WHERE conrelid = 'assignments'::regclass AND contype = 'c'
                     AND position('revision_required' in pg_get_constraintdef(oid)) > 0
          LOOP
            EXECUTE 'ALTER TABLE assignments DROP CONSTRAINT ' || quote_ident(c.conname);
          END LOOP;
        END $$;;

ALTER TABLE assignments ADD CONSTRAINT assignment_status CHECK (status IN ('assigned', 'in_progress', 'submitted', 'approved', 'revision_required', 'completed', 'reassigned'));

DO $$
        DECLARE c record;
        BEGIN
          FOR c IN SELECT conname FROM pg_constraint
                   WHERE conrelid = 'assignment_assignees'::regclass AND contype = 'c'
                     AND position('revision_required' in pg_get_constraintdef(oid)) > 0
          LOOP
            EXECUTE 'ALTER TABLE assignment_assignees DROP CONSTRAINT ' || quote_ident(c.conname);
          END LOOP;
        END $$;;

ALTER TABLE assignment_assignees ADD CONSTRAINT assignee_status CHECK (status IN ('assigned', 'in_progress', 'submitted', 'approved', 'revision_required', 'completed', 'reassigned'));

ALTER TABLE reviews ADD COLUMN rating INTEGER;

CREATE TABLE feedback_phrases (
    id SERIAL NOT NULL, 
    text VARCHAR(200) NOT NULL, 
    position INTEGER DEFAULT '0' NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (text)
);

INSERT INTO feedback_phrases (text, position) VALUES ('Fix lighting', 0);

INSERT INTO feedback_phrases (text, position) VALUES ('Check continuity', 1);

INSERT INTO feedback_phrases (text, position) VALUES ('Match the reference', 2);

INSERT INTO feedback_phrases (text, position) VALUES ('Clean up edges', 3);

INSERT INTO feedback_phrases (text, position) VALUES ('Timing feels off', 4);

INSERT INTO feedback_phrases (text, position) VALUES ('Great work', 5);

CREATE TABLE weekly_targets (
    user_id INTEGER NOT NULL, 
    scenes_per_week INTEGER NOT NULL, 
    set_by_id INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (user_id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    FOREIGN KEY(set_by_id) REFERENCES users (id) ON DELETE SET NULL
);

ALTER TABLE feedback_phrases ENABLE ROW LEVEL SECURITY;

ALTER TABLE weekly_targets ENABLE ROW LEVEL SECURITY;

UPDATE alembic_version SET version_num='9b6c7d8e0f15' WHERE alembic_version.version_num = '8a5b6c7d9e04';

-- Running upgrade 9b6c7d8e0f15 -> a0c7d8e9f126

UPDATE users SET role_id = (SELECT id FROM roles WHERE name = 'artist'),
                         job_title = COALESCE(job_title, 'Artist')
        WHERE role_id = (SELECT id FROM roles WHERE name = 'student');

DELETE FROM roles WHERE name = 'student';

DO $$
        DECLARE c record;
        BEGIN
          FOR c IN SELECT conname FROM pg_constraint
                   WHERE conrelid = 'roles'::regclass AND contype = 'c'
                     AND position('team_lead' in pg_get_constraintdef(oid)) > 0
          LOOP
            EXECUTE 'ALTER TABLE roles DROP CONSTRAINT ' || quote_ident(c.conname);
          END LOOP;
        END $$;;

ALTER TABLE roles ADD CONSTRAINT role_name CHECK (name IN ('admin', 'team_lead', 'artist'));

ALTER TABLE users RENAME student_code TO employee_code;

ALTER INDEX IF EXISTS ix_users_student_code RENAME TO ix_users_employee_code;

ALTER TABLE users DROP CONSTRAINT fk_users_batch_id_batches;

DROP INDEX ix_users_batch_id;

ALTER TABLE users DROP COLUMN batch_id;

ALTER TABLE users DROP COLUMN roll_number;

DROP TABLE holiday_batches;

CREATE TABLE holiday_teams (
    holiday_id INTEGER NOT NULL, 
    team_id INTEGER NOT NULL, 
    PRIMARY KEY (holiday_id, team_id), 
    FOREIGN KEY(holiday_id) REFERENCES holidays (id) ON DELETE CASCADE, 
    FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE CASCADE
);

DROP TABLE announcement_batches;

CREATE TABLE announcement_teams (
    announcement_id INTEGER NOT NULL, 
    team_id INTEGER NOT NULL, 
    PRIMARY KEY (announcement_id, team_id), 
    FOREIGN KEY(announcement_id) REFERENCES announcements (id) ON DELETE CASCADE, 
    FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE CASCADE
);

UPDATE holidays SET applies_to_all = true;

UPDATE announcements SET applies_to_all = true;

DROP TABLE student_attendance;

DROP TABLE batches;

ALTER TABLE leave_requests RENAME student_id TO user_id;

ALTER INDEX IF EXISTS ix_leave_requests_student_id RENAME TO ix_leave_requests_user_id;

ALTER TABLE attendance ADD COLUMN work_note TEXT;

ALTER TABLE holiday_teams ENABLE ROW LEVEL SECURITY;

ALTER TABLE announcement_teams ENABLE ROW LEVEL SECURITY;

UPDATE alembic_version SET version_num='a0c7d8e9f126' WHERE alembic_version.version_num = '9b6c7d8e0f15';

-- Running upgrade a0c7d8e9f126 -> b1d8e9f0a237

ALTER TABLE daily_reports ADD COLUMN auto_generated BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE daily_reports ADD COLUMN issues TEXT;

ALTER TABLE daily_reports ADD COLUMN submitted_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE daily_reports ADD COLUMN submitted_by_id INTEGER;

ALTER TABLE daily_reports ADD FOREIGN KEY(submitted_by_id) REFERENCES users (id);

ALTER TABLE daily_reports ADD COLUMN admin_comment TEXT;

ALTER TABLE daily_reports ADD COLUMN admin_commented_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE daily_reports ADD COLUMN admin_commented_by_id INTEGER;

ALTER TABLE daily_reports ADD FOREIGN KEY(admin_commented_by_id) REFERENCES users (id);

UPDATE alembic_version SET version_num='b1d8e9f0a237' WHERE alembic_version.version_num = 'a0c7d8e9f126';

-- Running upgrade b1d8e9f0a237 -> c2e9f0a1b348

ALTER TABLE users ADD COLUMN failed_logins INTEGER DEFAULT '0' NOT NULL;

ALTER TABLE users ADD COLUMN locked_until TIMESTAMP WITH TIME ZONE;

ALTER TABLE users ADD COLUMN totp_secret VARCHAR(255);

ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN DEFAULT false NOT NULL;

CREATE TABLE known_devices (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    fingerprint VARCHAR(64) NOT NULL, 
    user_agent VARCHAR(300), 
    ip VARCHAR(64), 
    first_seen_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_known_devices_user_id ON known_devices (user_id);

ALTER TABLE known_devices ENABLE ROW LEVEL SECURITY;

UPDATE alembic_version SET version_num='c2e9f0a1b348' WHERE alembic_version.version_num = 'b1d8e9f0a237';

-- Running upgrade c2e9f0a1b348 -> d3f0a1b2c459

CREATE TABLE chat_messages (
    id SERIAL NOT NULL, 
    channel VARCHAR(40) NOT NULL, 
    sender_id INTEGER NOT NULL, 
    body TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    edited_at TIMESTAMP WITH TIME ZONE, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    deleted_by_id INTEGER, 
    PRIMARY KEY (id), 
    FOREIGN KEY(sender_id) REFERENCES users (id), 
    FOREIGN KEY(deleted_by_id) REFERENCES users (id)
);

CREATE INDEX ix_chat_messages_channel_id ON chat_messages (channel, id);

CREATE INDEX ix_chat_messages_sender_id ON chat_messages (sender_id);

CREATE INDEX ix_chat_messages_created_at ON chat_messages (created_at);

CREATE TABLE chat_reads (
    user_id INTEGER NOT NULL, 
    channel VARCHAR(40) NOT NULL, 
    last_read_id INTEGER DEFAULT '0' NOT NULL, 
    PRIMARY KEY (user_id, channel), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;

ALTER TABLE chat_reads ENABLE ROW LEVEL SECURITY;

UPDATE alembic_version SET version_num='d3f0a1b2c459' WHERE alembic_version.version_num = 'c2e9f0a1b348';

-- Running upgrade d3f0a1b2c459 -> e4a1b2c3d560

CREATE TABLE project_characters (
    id SERIAL NOT NULL, 
    project_id INTEGER NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_project_character_name UNIQUE (project_id, name), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
);

CREATE INDEX ix_project_characters_project_id ON project_characters (project_id);

CREATE TABLE project_locations (
    id SERIAL NOT NULL, 
    project_id INTEGER NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_project_location_name UNIQUE (project_id, name), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
);

CREATE INDEX ix_project_locations_project_id ON project_locations (project_id);

ALTER TABLE scenes ADD COLUMN status_override VARCHAR(20);

ALTER TABLE scenes ADD COLUMN duration_sec FLOAT;

ALTER TABLE scenes ADD COLUMN frame_in INTEGER;

ALTER TABLE scenes ADD COLUMN frame_out INTEGER;

ALTER TABLE scenes ADD COLUMN fps FLOAT;

ALTER TABLE scenes ADD COLUMN reference_links JSONB DEFAULT '[]' NOT NULL;

ALTER TABLE scenes ADD COLUMN location_id INTEGER;

CREATE INDEX ix_scenes_location_id ON scenes (location_id);

ALTER TABLE scenes ADD CONSTRAINT fk_scenes_location_id_project_locations FOREIGN KEY(location_id) REFERENCES project_locations (id) ON DELETE SET NULL;

CREATE TABLE scene_characters (
    scene_id INTEGER NOT NULL, 
    character_id INTEGER NOT NULL, 
    PRIMARY KEY (scene_id, character_id), 
    FOREIGN KEY(scene_id) REFERENCES scenes (id) ON DELETE CASCADE, 
    FOREIGN KEY(character_id) REFERENCES project_characters (id) ON DELETE CASCADE
);

CREATE TABLE scene_prompts (
    id SERIAL NOT NULL, 
    scene_id INTEGER NOT NULL, 
    version INTEGER NOT NULL, 
    prompt TEXT NOT NULL, 
    tool VARCHAR(80), 
    seed VARCHAR(80), 
    settings TEXT, 
    notes TEXT, 
    created_by_id INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_scene_prompt_version UNIQUE (scene_id, version), 
    FOREIGN KEY(scene_id) REFERENCES scenes (id) ON DELETE CASCADE, 
    FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_scene_prompts_scene_id ON scene_prompts (scene_id);

ALTER TABLE project_characters ENABLE ROW LEVEL SECURITY;

ALTER TABLE project_locations ENABLE ROW LEVEL SECURITY;

ALTER TABLE scene_characters ENABLE ROW LEVEL SECURITY;

ALTER TABLE scene_prompts ENABLE ROW LEVEL SECURITY;

UPDATE alembic_version SET version_num='e4a1b2c3d560' WHERE alembic_version.version_num = 'd3f0a1b2c459';

COMMIT;


-- Seed basic roles
INSERT INTO roles (name, description) VALUES
  ('admin', 'Studio administration: manages people, teams, projects and settings'),
  ('team_lead', 'Leads one or more teams: assigns work, reviews deliverables, drafts daily reports'),
  ('artist', 'Studio artist: logs attendance, works on assignments, submits deliverables')
ON CONFLICT (name) DO NOTHING;

-- Seed default feedback phrases
INSERT INTO feedback_phrases (text, position) VALUES
  ('Fix lighting', 0),
  ('Check continuity', 1),
  ('Match the reference', 2),
  ('Clean up edges', 3),
  ('Timing feels off', 4),
  ('Great work', 5)
ON CONFLICT (text) DO NOTHING;
