import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query"
import { toast } from "sonner"

import { api, errorMessage } from "./api"
import { useAuth } from "./auth-context"
import type {
  ActivityEntry, AppNotification, FeedbackPhrase, LeadToday, WeeklyTarget, ArtistOverview, Assignment, EmailLogEntry, Report, ReportListItem, ReportMetrics, Submission, AttendanceRecord, DailyCount, ProjectDetail, Project, Recipient, RosterRow,
  StaffOverview, Team, TodayStatus, User, Announcement, Holiday, Leave, MonthStats, TeamReportStatus,
} from "./types"

export const keys = {
  users: (f?: object) => ["users", f ?? {}] as const,
  teams: ["teams"] as const,
  recipients: ["recipients"] as const,
  projects: (f?: object) => ["projects", f ?? {}] as const,
  project: (id: number) => ["project", id] as const,
  assignments: (f?: object) => ["assignments", f ?? {}] as const,
  assignment: (id: number) => ["assignment", id] as const,
  today: ["attendance", "today"] as const,
  myAttendance: (f?: object) => ["attendance", "me", f ?? {}] as const,
  userAttendance: (id: number, f?: object) => ["attendance", "user", id, f ?? {}] as const,
  roster: (f?: object) => ["attendance", "roster", f ?? {}] as const,
  attendanceSummary: (f?: object) => ["attendance", "summary", f ?? {}] as const,
  staffOverview: (f?: object) => ["dashboard", "overview", f ?? {}] as const,
  artistOverview: ["dashboard", "me"] as const,
  submissions: (f?: object) => ["submissions", f ?? {}] as const,
  submission: (id: number) => ["submission", id] as const,
  notifications: (f?: object) => ["notifications", f ?? {}] as const,
  unread: ["notifications", "unread"] as const,
  emailLogs: (f?: object) => ["email-logs", f ?? {}] as const,
  reports: (f?: object) => ["reports", f ?? {}] as const,
  report: (id: number) => ["report", id] as const,
  reportMetrics: (f?: object) => ["report-metrics", f ?? {}] as const,
  holidays: (f?: object) => ["holidays", f ?? {}] as const,
  leave: (f?: object) => ["leave", "list", f ?? {}] as const,
  myLeave: ["leave", "me"] as const,
  myMonth: ["attendance", "me", "month"] as const,
  announcements: (f?: object) => ["announcements", f ?? {}] as const,
  myAnnouncements: ["announcements", "me"] as const,
  teamReportStatus: (f?: object) => ["reports", "team-status", f ?? {}] as const,
  activity: (f?: object) => ["activity", f ?? {}] as const,
  leadToday: ["dashboard", "lead-today"] as const,
  myTarget: ["dashboard", "my-target"] as const,
  feedbackPhrases: ["feedback-phrases"] as const,
}

type Q = Record<string, string | number | boolean | undefined | null>

export const useUsers = (f: Q = {}, enabled = true) =>
  useQuery({ queryKey: keys.users(f), queryFn: () => api.get<User[]>("/users", f), enabled })
export const useTeams = () => useQuery({ queryKey: keys.teams, queryFn: () => api.get<Team[]>("/teams") })
export const useRecipients = () => useQuery({ queryKey: keys.recipients, queryFn: () => api.get<Recipient[]>("/recipients") })
export const useProjects = (f: Q = {}) => useQuery({ queryKey: keys.projects(f), queryFn: () => api.get<Project[]>("/projects", f) })
export const useProject = (id: number | undefined) =>
  useQuery({ queryKey: keys.project(id ?? 0), queryFn: () => api.get<ProjectDetail>(`/projects/${id}`), enabled: !!id })
export const useAssignments = (f: Q = {}) =>
  useQuery({ queryKey: keys.assignments(f), queryFn: () => api.get<Assignment[]>("/assignments", f) })
export const useToday = () => useQuery({ queryKey: keys.today, queryFn: () => api.get<TodayStatus>("/attendance/today") })
export const useMyAttendance = (f: Q = {}) =>
  useQuery({ queryKey: keys.myAttendance(f), queryFn: () => api.get<AttendanceRecord[]>("/attendance/me", f) })
export const useUserAttendance = (id: number | undefined, f: Q = {}) =>
  useQuery({ queryKey: keys.userAttendance(id ?? 0, f), queryFn: () => api.get<AttendanceRecord[]>(`/attendance/users/${id}`, f), enabled: !!id })
export const useRoster = (f: Q = {}) => useQuery({ queryKey: keys.roster(f), queryFn: () => api.get<RosterRow[]>("/attendance/roster", f) })
export const useAttendanceSummary = (f: Q = {}) =>
  useQuery({ queryKey: keys.attendanceSummary(f), queryFn: () => api.get<DailyCount[]>("/attendance/summary", f) })
export const useStaffOverview = (f: Q = {}) =>
  useQuery({ queryKey: keys.staffOverview(f), queryFn: () => api.get<StaffOverview>("/dashboard/overview", f), refetchInterval: 60_000 })
export const useArtistOverview = () =>
  useQuery({ queryKey: keys.artistOverview, queryFn: () => api.get<ArtistOverview>("/dashboard/me"), refetchInterval: 60_000 })

export const useSubmissions = (f: Q = {}, enabled = true) =>
  useQuery({ queryKey: keys.submissions(f), queryFn: () => api.get<Submission[]>("/submissions", f), enabled })
export const useSubmission = (id: number | undefined) =>
  useQuery({ queryKey: keys.submission(id ?? 0), queryFn: () => api.get<Submission>(`/submissions/${id}`), enabled: !!id })

export const useNotifications = (f: Q = {}) =>
  useQuery({ queryKey: keys.notifications(f), queryFn: () => api.get<AppNotification[]>("/notifications", f), refetchInterval: 30_000 })
export const useUnreadCount = () =>
  useQuery({ queryKey: keys.unread, queryFn: () => api.get<{ unread: number }>("/notifications/unread-count"), refetchInterval: 30_000 })
export const useEmailLogs = (f: Q = {}, enabled = true) =>
  useQuery({ queryKey: keys.emailLogs(f), queryFn: () => api.get<EmailLogEntry[]>("/email-logs", f), enabled, refetchInterval: 15_000 })

export const useReports = (f: Q = {}) =>
  useQuery({ queryKey: keys.reports(f), queryFn: () => api.get<ReportListItem[]>("/reports", f) })
export const useReport = (id: number | undefined) =>
  useQuery({ queryKey: keys.report(id ?? 0), queryFn: () => api.get<Report>(`/reports/${id}`), enabled: !!id })
export const useReportMetrics = (f: Q = {}) =>
  useQuery({ queryKey: keys.reportMetrics(f), queryFn: () => api.get<ReportMetrics>("/reports/metrics", f) })

export const useTeamReportStatus = (f: Q = {}, enabled = true) =>
  useQuery({ queryKey: keys.teamReportStatus(f), queryFn: () => api.get<TeamReportStatus[]>("/reports/team-status", f), enabled, refetchInterval: 60_000 })

export const useMyMonth = () => useQuery({ queryKey: keys.myMonth, queryFn: () => api.get<MonthStats>("/attendance/me/month") })
export const useLeave = (f: Q = {}, enabled = true) =>
  useQuery({ queryKey: keys.leave(f), queryFn: () => api.get<Leave[]>("/leave", f), enabled, refetchInterval: 60_000 })
export const useMyLeave = () => useQuery({ queryKey: keys.myLeave, queryFn: () => api.get<Leave[]>("/me/leave") })
export const useAnnouncements = (f: Q = {}) =>
  useQuery({ queryKey: keys.announcements(f), queryFn: () => api.get<Announcement[]>("/announcements", f) })
export const useMyAnnouncements = () =>
  useQuery({ queryKey: keys.myAnnouncements, queryFn: () => api.get<Announcement[]>("/me/announcements"), refetchInterval: 60_000, refetchOnWindowFocus: true })
export const useLeadToday = (enabled = true) =>
  useQuery({ queryKey: keys.leadToday, queryFn: () => api.get<LeadToday>("/lead/today"), enabled, refetchInterval: 60_000 })
export const useMyTarget = () =>
  useQuery({ queryKey: keys.myTarget, queryFn: () => api.get<WeeklyTarget>("/me/target"), refetchInterval: 300_000 })
export const useFeedbackPhrases = (enabled = true) =>
  useQuery({ queryKey: keys.feedbackPhrases, queryFn: () => api.get<FeedbackPhrase[]>("/feedback-phrases"), enabled, staleTime: 300_000 })

export const ACTIVITY_PAGE = 100
/** Audit trail, newest first; each next page asks for entries older than the last id seen. */
export const useActivity = (f: Q = {}) =>
  useInfiniteQuery({
    queryKey: keys.activity(f),
    queryFn: ({ pageParam }) => api.get<ActivityEntry[]>("/activity", { ...f, limit: ACTIVITY_PAGE, before_id: pageParam ?? undefined }),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => (last.length < ACTIVITY_PAGE ? undefined : last[last.length - 1].id),
  })
export const useHolidays = (f: Q = {}) => useQuery({ queryKey: keys.holidays(f), queryFn: () => api.get<Holiday[]>("/holidays", f) })

/** A holiday changes day-off status in rosters and dashboards. */
export const HOLIDAY_KEYS = [["holidays"], ["attendance"], ["dashboard"]]
/** A leave decision changes rosters, month stats, the lead's Today panel and reports. */
export const LEAVE_KEYS = [["leave"], ["attendance"], ["dashboard"], ["notifications"]]

/** Everything a submission or review can change. */
export const WORK_KEYS = [["submissions"], ["submission"], ["assignments"], ["assignment"], ["dashboard"], ["project"], ["notifications"]]

/** Studio setting: whether check-in / check-out clock times are shown anywhere (status always is). */
export const useShowCheckinTimes = () => Boolean(useAuth().config?.show_checkin_times)

/**
 * Mutation with toast feedback and cache invalidation.
 * `invalidate` lists query-key prefixes to refresh on success.
 */
export function useAction<TVars, TResult = unknown>(
  fn: (vars: TVars) => Promise<TResult>,
  opts: { success?: string | ((r: TResult) => string); invalidate?: QueryKey[]; onSuccess?: (r: TResult) => void } = {},
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (r) => {
      opts.invalidate?.forEach((k) => qc.invalidateQueries({ queryKey: k }))
      if (opts.success) toast.success(typeof opts.success === "function" ? opts.success(r) : opts.success)
      opts.onSuccess?.(r)
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
}
