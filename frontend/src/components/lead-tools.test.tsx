import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AssignmentDetailDialog } from "@/components/assignment-detail"
import { LeadTodayPanel } from "@/components/lead-today"
import { WeeklyTargetBar } from "@/components/weekly-target"
import type { Assignment, LeadToday, Submission } from "@/lib/types"
import ReviewsPage from "@/pages/reviews"

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ user: { id: 2, role: "team_lead", full_name: "Priya Raman" }, config: { studio_today: "2026-11-20", eod_deadline_hour: 19 } }),
}))

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }))

const wrap = (ui: React.ReactNode) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter>{ui}</MemoryRouter>
  </QueryClientProvider>
)

const today: LeadToday = {
  date: "2026-11-20", is_work_day: true,
  counts: { reviews: 1, leave_requests: 1, overdue: 1, due_today: 0, absent: 2 },
  reviews: [{ submission_id: 7, person: "Arjun Mehta", assignment: "EP01 Pilot — SC01", submitted_at: "2026-11-20T05:00:00Z", late: true }],
  leave_requests: [{
    id: 9, user_id: 5, person: "Asha Rao", team_id: 1, team_name: "Animation Unit", start: "2026-11-24", end: "2026-11-25",
    days: 2, reason: "Family function", status: "pending", decided_by: null, decided_at: null, decision_note: null, created_at: "2026-11-20T03:00:00Z",
  }],
  overdue: [{ assignment_id: 42, title: "Storyboard practice", person: "Asha Rao", person_id: 5, deadline: "2026-11-19T13:30:00Z", status: "in_progress" }],
  due_today: [],
  absent: [
    { person_id: 4, person: "Arjun Mehta", status: "not_checked_in" },
    { person_id: 5, person: "Asha Rao", status: "absent" },
  ],
}

const assignment: Assignment = {
  id: 42, title: "Storyboard practice", project_id: 1, project_title: "Neon", project_code: "NEON-01",
  episode_id: null, episode_number: null, episode_title: null, description: "Draw 6 panels", expected_deliverables: null,
  assignment_date: "2026-11-20", deadline: "2026-11-21T13:30:00Z", priority: "medium", status: "assigned", is_overdue: false,
  created_by_id: 2, created_by_name: "Priya Raman", created_at: "2026-11-20T04:00:00Z", scenes: [],
  assignees: [
    { id: 1, user_id: 4, full_name: "Arjun Mehta", status: "in_progress", reported_progress_pct: 20, progress_note: null, scenes_submitted: 0, scenes_approved: 0, scene_states: {} },
    { id: 2, user_id: 6, full_name: "Old Holder", status: "reassigned", reported_progress_pct: 0, progress_note: null, scenes_submitted: 1, scenes_approved: 0, scene_states: {} },
  ],
}

const sub: Submission = {
  id: 7, assignment_id: 3, assignment_title: "EP01 Pilot — SC01", project_id: 1, project_title: "Neon", project_code: "NEON-01",
  episode_number: 1, episode_title: "Pilot", artist_id: 4, artist_name: "Arjun Mehta", revision_number: 1,
  previous_submission_id: null, is_resubmission: false, submitted_at: "2026-11-20T05:00:00Z", submission_date: "2026-11-20",
  is_late: false, deadline: "2026-11-20T13:30:00Z", scenes_completed_count: 1, work_description: "Rendered",
  output_links: [], comments: null, status: "pending_review",
  deliverables: [{ id: 1, scene_id: 11, label: "EP01 SC01", status: "submitted", approved_at: null, approved_by_name: null }],
  attachments: [], reviews: [],
}

describe("team-lead tools", () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock)
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} })
  })
  afterEach(() => { fetchMock.mockReset(); vi.unstubAllGlobals() })

  it("Today panel shows counts and links", async () => {
    fetchMock.mockImplementation((url: string) => (url === "/api/v1/lead/today" ? json(200, today) : json(404, {})))
    render(wrap(<LeadTodayPanel />))

    expect(await screen.findByLabelText("Reviews waiting: 1")).toBeInTheDocument()
    expect(screen.getByLabelText("Absent / not checked in: 2")).toBeInTheDocument()
    expect(screen.getByLabelText("Overdue & due today: 1")).toBeInTheDocument()

    const review = screen.getByRole("link", { name: /Arjun Mehta.*EP01 Pilot/ })
    expect(review).toHaveAttribute("href", "/lead/reviews?open=7")
    expect(within(review).getByText("late")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Storyboard practice/ })).toHaveAttribute("href", "/lead/assignments?open=42")
    expect(screen.getByRole("link", { name: /Family function/ })).toHaveAttribute("href", "/lead/leave")
    const absent = screen.getByRole("link", { name: /Asha Rao.*Absent/ })
    expect(absent).toHaveAttribute("href", "/lead/attendance")
    expect(within(absent).queryByText("Student")).not.toBeInTheDocument()
  })

  it("Today panel says All clear for empty sections", async () => {
    const empty = { ...today, counts: { reviews: 0, leave_requests: 0, overdue: 0, due_today: 0, absent: 0 }, reviews: [], leave_requests: [], overdue: [], absent: [] }
    fetchMock.mockImplementation(() => json(200, empty))
    render(wrap(<LeadTodayPanel />))
    expect(await screen.findAllByText("All clear")).toHaveLength(4)
  })

  it("review sends the star rating and appends clicked phrases to the feedback", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith("/review") && init?.method === "POST") return json(200, { ...sub, status: "approved" })
      if (url === "/api/v1/feedback-phrases") return json(200, [{ id: 1, text: "Great timing." }, { id: 2, text: "Check the lighting." }])
      if (url.startsWith("/api/v1/submissions")) return json(200, [sub])
      return json(404, {})
    })
    render(wrap(<ReviewsPage />))

    await userEvent.click(await screen.findByRole("button", { name: "+ Great timing." }))
    await userEvent.click(screen.getByRole("button", { name: "+ Check the lighting." }))
    expect(screen.getByLabelText("Feedback for the assignee")).toHaveValue("Great timing. Check the lighting.")
    await userEvent.click(screen.getByRole("radio", { name: "4 stars" }))
    expect(screen.getByRole("radio", { name: "4 stars" })).toHaveAttribute("aria-checked", "true")
    await userEvent.click(screen.getByRole("button", { name: /^Approve$/ }))

    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/submissions/7/review"))).toBe(true))
    const [, init] = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/submissions/7/review"))!
    expect(JSON.parse(init.body)).toEqual({ decision: "approved", feedback: "Great timing. Check the lighting.", approved_scene_ids: [11], rating: 4 })
  })

  it("reassign dialog sends from/to/note and is disabled for reassigned slots", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith("/reassign") && init?.method === "POST") return json(200, assignment)
      if (url.startsWith("/api/v1/users")) return json(200, [{ id: 4, full_name: "Arjun Mehta", employee_code: null }, { id: 5, full_name: "Asha Rao", employee_code: "EMP001" }])
      return json(200, [])
    })
    render(wrap(<AssignmentDetailDialog assignment={assignment} viewerId={2} canManage onClose={() => {}} />))

    expect(screen.getByText("Reassigned")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Reassign Old Holder" })).toBeDisabled()
    await userEvent.click(screen.getByRole("button", { name: "Reassign Arjun Mehta" }))
    const select = await screen.findByLabelText("New person")
    await screen.findByRole("option", { name: "Asha Rao · EMP001" })
    expect(within(select).queryByRole("option", { name: "Arjun Mehta" })).not.toBeInTheDocument() // already on it
    await userEvent.selectOptions(select, "5")
    await userEvent.type(screen.getByLabelText("Note (optional)"), "Arjun is on leave")
    await userEvent.click(screen.getByRole("button", { name: /^Reassign$/ }))

    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => u === "/api/v1/assignments/42/reassign")).toBe(true))
    const [, init] = fetchMock.mock.calls.find(([u]) => u === "/api/v1/assignments/42/reassign")!
    expect(JSON.parse(init.body)).toEqual({ from_user_id: 4, to_user_id: 5, note: "Arjun is on leave" })
  })

  it("worker target bar shows progress, and hides without a target", async () => {
    fetchMock.mockImplementation(() => json(200, { week_start: "2026-11-16", week_end: "2026-11-22", target: 5, approved: 3 }))
    const { unmount } = render(wrap(<WeeklyTargetBar />))
    expect(await screen.findByText("3 / 5")).toBeInTheDocument()
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "3")
    unmount()

    fetchMock.mockImplementation(() => json(200, { week_start: "2026-11-16", week_end: "2026-11-22", target: null, approved: 3 }))
    render(wrap(<WeeklyTargetBar />))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument()
    expect(screen.queryByText(/This week/)).not.toBeInTheDocument()
  })
})
