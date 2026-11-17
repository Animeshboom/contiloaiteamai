import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query"
import { toast } from "sonner"

import { api, errorMessage } from "./api"
import type {
  ArtistOverview, Assignment, Submission, AttendanceRecord, DailyCount, ProjectDetail, Project, Recipient, RosterRow,
  StaffOverview, Team, TodayStatus, User,
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

/** Everything a submission or review can change. */
export const WORK_KEYS = [["submissions"], ["submission"], ["assignments"], ["assignment"], ["dashboard"], ["project"]]

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
