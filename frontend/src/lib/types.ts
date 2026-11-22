/** Mirrors backend Pydantic schemas (app/schemas). */

export type Role = "admin" | "team_lead" | "artist"

export interface TeamRef { id: number; name: string }

export interface User {
  id: number
  email: string
  full_name: string
  role: Role
  job_title: string | null
  team: TeamRef | null
  /** Login ID for people without an email (EMP001) */
  employee_code: string | null
  phone: string | null
  is_active: boolean
  last_login_at: string | null
  created_at: string
  /** Set while the account is locked after too many wrong passwords (in the past = no longer locked). */
  locked_until?: string | null
  /** Two-step login (authenticator app) is on — admins only. */
  mfa_enabled?: boolean
}

/** POST /auth/login, /auth/login/mfa, /auth/mfa/enable */
export interface TokenResponse {
  access_token: string | null
  mfa_required?: boolean
  mfa_token?: string | null
  user: User
}

export interface UserBrief { id: number; full_name: string; email: string; job_title: string | null }

export interface Team {
  id: number
  name: string
  department: string | null
  description: string | null
  lead: UserBrief | null
  member_count: number
  created_at: string
}

export interface Recipient { id: number; email: string; name: string; purpose: string; is_active: boolean }

export type ProjectType = "feature_film" | "series" | "short_film" | "commercial" | "music_video" | "other"
export type ProjectStatus = "planning" | "active" | "on_hold" | "completed" | "archived"
export type WorkStatus = "not_started" | "in_progress" | "in_review" | "approved" | "completed"

export interface Scene {
  id: number; episode_id: number; scene_number: number; label: string
  title: string | null; description: string | null; status: WorkStatus
  duration_sec?: number | null; reference_links?: { label: string; url: string }[]
  characters?: string[]
}

export interface Episode {
  id: number; project_id: number; episode_number: number; title: string
  description: string | null; status: WorkStatus; scenes: Scene[]
}

export interface Project {
  id: number; code: string; title: string; description: string | null
  project_type: ProjectType; status: ProjectStatus
  start_date: string | null; expected_completion_date: string | null
  team_id: number | null; team_name: string | null; created_at: string
  episode_count: number; scene_count: number; can_manage: boolean
}

export interface ProjectDetail extends Project { episodes: Episode[] }

export type AttendanceStatus = "present" | "absent" | "half_day" | "leave"

export interface AttendanceRecord {
  id: number; user_id: number; work_date: string
  check_in_at: string | null; check_out_at: string | null
  status: AttendanceStatus; notes: string | null
  /** the person's own check-out note: what they did, any blockers */
  work_note?: string | null
  corrected_by_id: number | null; corrected_at: string | null; worked_minutes: number | null
}

export interface TodayStatus { work_date: string; record: AttendanceRecord | null; can_check_in: boolean; can_check_out: boolean }

export interface RosterRow {
  user_id: number; full_name: string; job_title: string | null; team_name: string | null
  status: AttendanceStatus | "not_checked_in" | "day_off"; record: AttendanceRecord | null
  month?: MonthStats
}

/** This month so far: present days (half days count 0.5) out of working days already decided. */
export interface MonthStats { month: string; present: number; counted_days: number; pct: number | null; low: boolean }

export interface DailyCount { date: string; present: number; half_day: number; leave: number; absent: number }

export type Priority = "low" | "medium" | "high" | "urgent"
/** "reassigned" only appears per assignee: the slot was handed to someone else after they had submitted. */
export type AssignmentStatus = "assigned" | "in_progress" | "submitted" | "approved" | "revision_required" | "completed" | "reassigned"

export interface SceneRef { id: number; scene_number: number; label: string; title: string | null; episode_id: number; episode_number: number }

export interface Assignee {
  id: number; user_id: number; full_name: string; status: AssignmentStatus
  reported_progress_pct: number; progress_note: string | null
  scenes_submitted: number; scenes_approved: number
  /** scene_id -> latest state from submissions/reviews */
  scene_states: Record<string, SceneState>
}

export type SceneState = "submitted" | "approved" | "rejected"
export type SubmissionStatus = "pending_review" | "approved" | "rejected"

export interface Deliverable {
  id: number; scene_id: number | null; label: string; status: SceneState
  approved_at: string | null; approved_by_name: string | null
}

export interface Attachment { id: number; original_filename: string; content_type: string | null; size_bytes: number; created_at: string }

export interface Review {
  id: number; reviewer_id: number; reviewer_name: string; decision: "approved" | "rejected"
  feedback: string | null; approved_scene_ids: number[]; created_at: string
  /** 1-5; only returned to leads/admins */
  rating?: number | null
}

export interface Submission {
  id: number; assignment_id: number; assignment_title: string
  project_id: number; project_title: string; project_code: string
  episode_number: number | null; episode_title: string | null
  artist_id: number; artist_name: string
  revision_number: number; previous_submission_id: number | null; is_resubmission: boolean
  submitted_at: string; submission_date: string; is_late: boolean; deadline: string
  scenes_completed_count: number; work_description: string; output_links: string[]; comments: string | null
  status: SubmissionStatus
  deliverables: Deliverable[]; attachments: Attachment[]; reviews: Review[]
}

export interface Assignment {
  id: number; title: string
  project_id: number; project_title: string; project_code: string
  episode_id: number | null; episode_number: number | null; episode_title: string | null
  description: string | null; expected_deliverables: string | null
  assignment_date: string; deadline: string; priority: Priority; status: AssignmentStatus; is_overdue: boolean
  created_by_id: number; created_by_name: string; created_at: string
  scenes: SceneRef[]; assignees: Assignee[]
}

export interface StaffOverview {
  date: string
  headcount: number
  attendance_today: Record<"present" | "half_day" | "leave" | "absent" | "not_checked_in" | "day_off", number>
  attendance_trend: DailyCount[]
  assignments_by_status: Record<AssignmentStatus, number>
  active_assignments: number
  due_today: number
  overdue: number
  pending_reviews: number
  active_projects: number
  workload: {
    user_id: number; full_name: string; active: number; submitted: number; approved: number
    approved_this_week?: number; weekly_target?: number | null; avg_rating?: number | null
  }[]
}

export interface ArtistOverview {
  date: string
  attendance: TodayStatus
  assignments_by_status: Record<AssignmentStatus, number>
  open_assignments: number
  awaiting_review: number
  overdue: number
}

export interface AppConfig {
  studio_timezone: string
  eod_deadline_hour: number
  studio_today: string
  email_provider: string
  gmail_backend: string
  ai_enabled: boolean
  max_upload_mb: number
  email_enabled: boolean
  auth_provider: "local" | "supabase"
  /** Show check-in / check-out clock times (still recorded either way). Off by default. */
  show_checkin_times: boolean
}

export interface AppNotification {
  id: number; event_type: string; title: string; message: string; link: string | null
  entity_type: string | null; entity_id: number | null; read_at: string | null; created_at: string
}

export type EmailStatus = "pending" | "sent" | "drafted" | "failed" | "blocked"

export interface EmailLogEntry {
  id: number; tool_name: string; provider: string; recipients: string[]; subject: string; status: EmailStatus
  provider_message_id: string | null; error: string | null; attempts: number
  entity_type: string | null; entity_id: number | null
  created_at: string; last_attempt_at: string | null; next_attempt_at: string | null; sent_at: string | null
}

export type ReportStatus = "draft" | "approved" | "sent" | "failed"
export type AiStatus = "generated" | "template" | "rejected_unverified_numbers" | "ai_error" | "refused"

export interface SlotRow { assignment_id: number; title: string; project: string; artist: string; deadline: string; status: AssignmentStatus; reported_progress_pct: number }

export interface ArtistMetrics {
  name: string; job_title: string | null; attendance: AttendanceStatus | "not_checked_in" | "day_off"
  check_in: string | null; check_out: string | null; worked_minutes: number | null
  active_assignments: number; scenes_assigned_today: number; scenes_submitted: number; scenes_approved: number
  scenes_rejected: number; pending_reviews: number; delayed_assignments: number; late_submissions: number
  reported_progress_pct: number | null
}

export interface ReportMetrics {
  report_date: string; generated_at: string; as_of: string
  scope: { teams: string[]; filters: Record<string, string> }
  totals: {
    team_members: number; present: number; half_day: number; on_leave: number; absent: number; not_checked_in: number; day_off?: number
    attendance_rate_pct: number | null; projects_worked_on: number; assignments_distributed: number; assignments_active: number
    scenes_assigned: number; scenes_submitted: number; deliverables_submitted: number; submissions: number
    scenes_approved: number; scenes_rejected: number; approval_rate_pct: number | null; pending_reviews: number
    incomplete_assignments: number; delayed_assignments: number; late_submissions: number
  }
  attendance_by_status: Record<string, string[]>
  projects: { code: string; title: string; assignments_active: number; assignments_distributed: number; scenes_submitted: number; scenes_approved: number; scenes_rejected: number }[]
  artists: ArtistMetrics[]
  incomplete_assignments: SlotRow[]
  delayed_assignments: SlotRow[]
  remarks: string[]
}

export interface ReportListItem {
  id: number; report_date: string; status: ReportStatus; subject: string; recipients: string[]
  ai_status: AiStatus | null; created_by_name: string; created_at: string; approved_at: string | null
  sent_at: string | null; sent_by_name: string | null; delivery_status: string | null; filters: Record<string, number>
  /** drafted by the 7 PM job for the lead */
  auto_generated?: boolean
  issues?: string | null
  submitted_at?: string | null; submitted_by_name?: string | null
  admin_comment?: string | null; admin_commented_at?: string | null; admin_commented_by_name?: string | null
}

export interface TeamReportStatus {
  lead_id: number; lead: string; teams: string[]; report_id: number | null; submitted_at: string | null; issues: string | null
}

export interface Report extends ReportListItem {
  metrics: ReportMetrics
  narrative: { summary: string; highlights: string[]; concerns: string[] }
  ai_note: string | null; body: string; approved_by_name: string | null
  gmail_message_id: string | null; gmail_draft_id: string | null; email_error: string | null
}

/* ---------- artist accounts, leave, holidays, announcements ---------- */

/** Returned once, when an artist account is created or its password reset. `login` is the email or Employee ID. */
export interface Credentials { user: User; login: string; password: string }

export interface ImportResult { created: Credentials[]; errors: { row: number; message: string }[] }

export interface Holiday { id: number; date: string; name: string; applies_to_all: boolean; teams: TeamRef[] }

export type LeaveStatus = "pending" | "approved" | "rejected" | "cancelled"
export type LeaveType = "casual" | "sick" | "privilege" | "unpaid"
export type HalfDayType = "first_half" | "second_half"

export interface Leave {
  id: number
  user_id: number
  person: string
  team_id: number | null
  team_name: string | null
  start: string
  end: string
  days: number
  reason: string
  leave_type?: LeaveType
  half_day?: HalfDayType | null
  active_tasks_count?: number
  team_overlap_count?: number
  days_taken_year?: number
  days_taken_month?: number
  status: LeaveStatus
  decided_by: string | null
  decided_at: string | null
  decision_note: string | null
  created_at: string
}

export interface Announcement {
  id: number; title: string; body: string; author: string | null; author_id: number | null
  applies_to_all: boolean; teams: TeamRef[]; show_until: string | null; created_at: string; active: boolean
}

export interface ActivityEntry {
  id: number; at: string; actor_id: number | null; actor: string; action: string; summary: string
  subject: string | null; details: Record<string, unknown> | null; ip: string | null
}

export interface LeadTaskItem { assignment_id: number; title: string; person: string; person_id: number; deadline: string; status: AssignmentStatus }

export interface LeadToday {
  date: string; is_work_day: boolean
  counts: { reviews: number; leave_requests: number; overdue: number; due_today: number; absent: number }
  reviews: { submission_id: number; person: string; assignment: string; submitted_at: string; late: boolean }[]
  leave_requests: Leave[]
  overdue: LeadTaskItem[]
  due_today: LeadTaskItem[]
  absent: { person_id: number; person: string; status: "absent" | "not_checked_in" }[]
}

export interface WeeklyTarget { week_start: string; week_end: string; target: number | null; approved: number }

export interface FeedbackPhrase { id: number; text: string }

/* ---------- chat (automatic group chats) ---------- */
export type ChatChannelKind = "everyone" | "leads" | "team"

export interface ChatMessage {
  id: number; channel: string; sender_id: number; sender: string
  /** null when deleted */
  body: string | null; created_at: string; edited_at: string | null; deleted: boolean
}

export interface ChatChannel {
  key: string; name: string; kind: ChatChannelKind; can_post: boolean; unread: number; last_message: ChatMessage | null
}
