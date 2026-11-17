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
  is_active: boolean
  last_login_at: string | null
  created_at: string
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
  corrected_by_id: number | null; corrected_at: string | null; worked_minutes: number | null
}

export interface TodayStatus { work_date: string; record: AttendanceRecord | null; can_check_in: boolean; can_check_out: boolean }

export interface RosterRow {
  user_id: number; full_name: string; job_title: string | null; team_name: string | null
  status: AttendanceStatus | "not_checked_in"; record: AttendanceRecord | null
}

export interface DailyCount { date: string; present: number; half_day: number; leave: number; absent: number }

export type Priority = "low" | "medium" | "high" | "urgent"
export type AssignmentStatus = "assigned" | "in_progress" | "submitted" | "approved" | "revision_required" | "completed"

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
  attendance_today: Record<"present" | "half_day" | "leave" | "absent" | "not_checked_in", number>
  attendance_trend: DailyCount[]
  assignments_by_status: Record<AssignmentStatus, number>
  active_assignments: number
  due_today: number
  overdue: number
  pending_reviews: number
  active_projects: number
  workload: { user_id: number; full_name: string; active: number; submitted: number; approved: number }[]
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
  ai_enabled: boolean
  max_upload_mb: number
}
