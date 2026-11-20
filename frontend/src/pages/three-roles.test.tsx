import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { CheckInCard } from "@/components/check-in-card"
import { MyLeaveCard } from "@/components/my-leave"
import { loginEmail } from "@/lib/supabase"
import type { Leave, Report, Role } from "@/lib/types"
import AnnouncementsPage from "./announcements"
import EmployeesPage from "./employees"
import LeavePage from "./leave"
import ReportDetailPage from "./report-detail"

const auth = vi.hoisted(() => ({ role: "admin" as Role, emailEnabled: false }))
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: { id: 2, role: auth.role, full_name: "Priya Raman", team: { id: 1, name: "Animation Unit" } },
    config: { studio_today: "2026-11-20", eod_deadline_hour: 19, email_enabled: auth.emailEnabled, email_provider: "mcp", gmail_backend: "mock" },
  }),
  useStudioDay: () => ["2026-11-20", () => {}, "2026-11-20"],
}))

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }))
const wrap = (ui: React.ReactNode, at = "/") => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[at]}>{ui}</MemoryRouter>
  </QueryClientProvider>
)
const bodyOf = (fetchMock: ReturnType<typeof vi.fn>, url: string) =>
  JSON.parse(String(fetchMock.mock.calls.find(([u, i]) => u === url && i?.method && i.method !== "GET")![1].body))
const sent = (fetchMock: ReturnType<typeof vi.fn>, url: string) =>
  fetchMock.mock.calls.some(([u, i]) => u === url && i?.method && i.method !== "GET")

const leave: Leave = {
  id: 9, user_id: 5, person: "Asha Rao", team_id: 1, team_name: "Animation Unit", start: "2026-11-24", end: "2026-11-25", days: 2,
  reason: "Family function", status: "pending", decided_by: null, decided_at: null, decision_note: null, created_at: "2026-11-20T03:00:00Z",
}

describe("three roles: admin, team lead, artist", () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock)
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} })
    auth.role = "admin"
    auth.emailEnabled = false
  })
  afterEach(() => { fetchMock.mockReset(); vi.unstubAllGlobals() })

  it("maps an Employee ID to the login email domain", () => {
    expect(loginEmail(" EMP001 ")).toBe("emp001@staff.studiotrack.app")
    expect(loginEmail("Priya@Studio.test")).toBe("priya@studio.test")
  })

  it("admin creates an artist with an Employee ID and sees the one-time credentials", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/v1/artists" && init?.method === "POST") {
        return json(201, { user: { id: 5, full_name: "Asha Rao", role: "artist", team: { id: 1, name: "Animation Unit" }, employee_code: "EMP007" }, login: "EMP007", password: "Kx7-pq2-Lm" })
      }
      if (url.startsWith("/api/v1/teams")) return json(200, [{ id: 1, name: "Animation Unit" }])
      return json(200, [])
    })
    render(wrap(<EmployeesPage />))

    await userEvent.click(screen.getByRole("button", { name: /Add artist/ }))
    await userEvent.type(screen.getByLabelText("Full name"), "Asha Rao")
    await userEvent.type(screen.getByLabelText("Employee ID (optional)"), "EMP007")
    expect(screen.getByLabelText("Email (optional)")).toBeDisabled() // one or the other
    await screen.findByRole("option", { name: "Animation Unit" })
    await userEvent.selectOptions(screen.getByLabelText("Team"), "1")
    await userEvent.click(screen.getByRole("button", { name: "Create account" }))

    await waitFor(() => expect(sent(fetchMock, "/api/v1/artists")).toBe(true))
    expect(bodyOf(fetchMock, "/api/v1/artists")).toEqual({
      full_name: "Asha Rao", email: null, employee_code: "EMP007", team_id: 1, job_title: "Artist", phone: null, password: null,
    })
    expect(await screen.findByText("Kx7-pq2-Lm")).toBeInTheDocument()
    expect(screen.getByText(/shown only once/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Download logins/ })).toBeInTheDocument()
  })

  it("a lead rejects leave only with a note", async () => {
    auth.role = "team_lead"
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith("/decide") && init?.method === "POST") return json(200, { ...leave, status: "rejected" })
      if (url.startsWith("/api/v1/leave")) return json(200, [leave])
      return json(200, [])
    })
    render(wrap(<LeavePage />))

    await userEvent.click(await screen.findByRole("button", { name: "Reject leave for Asha Rao" }))
    const reject = screen.getByRole("button", { name: "Reject" })
    expect(reject).toBeDisabled()
    await userEvent.type(screen.getByLabelText("Note for them"), "Delivery week")
    await userEvent.click(reject)
    await waitFor(() => expect(sent(fetchMock, "/api/v1/leave/9/decide")).toBe(true))
    expect(bodyOf(fetchMock, "/api/v1/leave/9/decide")).toEqual({ decision: "rejected", note: "Delivery week" })
  })

  it("anyone requests their own leave", async () => {
    auth.role = "artist"
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/v1/me/leave" && init?.method === "POST") return json(201, leave)
      return json(200, [])
    })
    render(wrap(<MyLeaveCard />))
    await userEvent.click(screen.getByRole("button", { name: /Request leave/ }))
    expect(screen.getByLabelText("From")).toHaveValue("2026-11-20")
    await userEvent.type(screen.getByLabelText("Reason"), "Family function")
    await userEvent.click(screen.getByRole("button", { name: "Send request" }))
    await waitFor(() => expect(sent(fetchMock, "/api/v1/me/leave")).toBe(true))
    expect(bodyOf(fetchMock, "/api/v1/me/leave")).toEqual({ start: "2026-11-20", end: "2026-11-20", reason: "Family function" })
  })

  it("check-out sends the optional end-of-day note", async () => {
    auth.role = "artist"
    const rec = { id: 1, user_id: 5, work_date: "2026-11-20", check_in_at: "2026-11-20T04:30:00Z", check_out_at: null, status: "present", notes: null,
      corrected_by_id: null, corrected_at: null, worked_minutes: null }
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/v1/attendance/check-out" && init?.method === "POST") return json(200, { ...rec, check_out_at: "2026-11-20T13:00:00Z", worked_minutes: 510 })
      if (url === "/api/v1/attendance/today") return json(200, { work_date: "2026-11-20", record: rec, can_check_in: false, can_check_out: true })
      return json(200, [])
    })
    render(wrap(<CheckInCard />))
    await userEvent.click(await screen.findByRole("button", { name: /Check out/ }))
    await userEvent.type(screen.getByLabelText("What did you do today? Any blockers?"), "Finished SC03; waiting on music")
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /Check out/ }))
    await waitFor(() => expect(sent(fetchMock, "/api/v1/attendance/check-out")).toBe(true))
    expect(bodyOf(fetchMock, "/api/v1/attendance/check-out")).toEqual({ note: "Finished SC03; waiting on music" })
  })

  it("lead posts an announcement to their team", async () => {
    auth.role = "team_lead"
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/v1/announcements" && init?.method === "POST") return json(201, { id: 1 })
      if (url.startsWith("/api/v1/teams")) return json(200, [{ id: 1, name: "Animation Unit", lead: { id: 2 } }, { id: 3, name: "VFX Unit", lead: { id: 9 } }])
      return json(200, [])
    })
    render(wrap(<AnnouncementsPage />))
    await waitFor(() => expect(screen.getByRole("button", { name: /New announcement/ })).toBeEnabled())
    await userEvent.click(screen.getByRole("button", { name: /New announcement/ }))
    expect(screen.queryByRole("checkbox", { name: "VFX Unit" })).not.toBeInTheDocument() // not their team
    expect(screen.getByRole("checkbox", { name: "Animation Unit" })).toBeChecked()
    await userEvent.type(screen.getByLabelText("Title"), "Studio closed Friday")
    await userEvent.type(screen.getByLabelText("Message"), "Power maintenance.")
    await userEvent.click(screen.getByRole("button", { name: "Post" }))
    await waitFor(() => expect(sent(fetchMock, "/api/v1/announcements")).toBe(true))
    expect(bodyOf(fetchMock, "/api/v1/announcements")).toEqual({ title: "Studio closed Friday", body: "Power maintenance.", team_ids: [1] })
  })

  describe("day report hand-off (email off)", () => {
    const report = {
      id: 9, report_date: "2026-11-20", status: "draft", subject: "Day report", recipients: [], ai_status: "template",
      created_by_name: "System", created_at: "2026-11-20T13:30:00Z", approved_at: null, sent_at: null, sent_by_name: null,
      delivery_status: null, filters: {}, ai_note: null, approved_by_name: null, gmail_message_id: null, gmail_draft_id: null,
      email_error: null, body: "SUMMARY\n...\nNOTES FROM THE TEAM\n- Asha: Finished SC03", auto_generated: true,
      narrative: { summary: "", highlights: [], concerns: [] },
      metrics: { report_date: "2026-11-20", generated_at: "", as_of: "end of day", scope: { teams: [], filters: {} },
        totals: { team_members: 1, present: 1, half_day: 0, on_leave: 0, absent: 0, not_checked_in: 0, attendance_rate_pct: 100,
          projects_worked_on: 0, assignments_distributed: 0, assignments_active: 0, scenes_assigned: 0, scenes_submitted: 0,
          deliverables_submitted: 0, submissions: 0, scenes_approved: 0, scenes_rejected: 0, approval_rate_pct: null,
          pending_reviews: 0, incomplete_assignments: 0, delayed_assignments: 0, late_submissions: 0 },
        attendance_by_status: {}, projects: [], artists: [], incomplete_assignments: [], delayed_assignments: [], remarks: [] },
    } as unknown as Report
    const renderAt = (base: string) => render(wrap(
      <Routes><Route path={`${base}/:id`} element={<ReportDetailPage />} /></Routes>, `${base}/9`,
    ))

    it("lead sends the report to the admin with issues; email controls are hidden", async () => {
      auth.role = "team_lead"
      fetchMock.mockImplementation((url: string, init?: RequestInit) => {
        if (url === "/api/v1/reports/9/submit") return json(200, { ...report, issues: "Render farm down", submitted_at: "2026-11-20T13:40:00Z" })
        if (url === "/api/v1/reports/9" && (init?.method ?? "GET") === "GET") return json(200, report)
        return json(200, [])
      })
      renderAt("/lead/reports")
      await userEvent.type(await screen.findByLabelText("Issues / remarks (optional)"), "Render farm down")
      expect(screen.queryByRole("button", { name: /Approve & send/ })).not.toBeInTheDocument()
      expect(screen.queryByText("Recipients")).not.toBeInTheDocument()
      await userEvent.click(screen.getByRole("button", { name: "Send to admin" }))
      await waitFor(() => expect(sent(fetchMock, "/api/v1/reports/9/submit")).toBe(true))
      expect(bodyOf(fetchMock, "/api/v1/reports/9/submit")).toEqual({ issues: "Render farm down" })
    })

    it("admin sees the issues first and can reply", async () => {
      const submitted = { ...report, issues: "Render farm down", submitted_at: "2026-11-20T13:40:00Z", submitted_by_name: "Priya Raman" }
      fetchMock.mockImplementation((url: string, init?: RequestInit) => {
        if (url === "/api/v1/reports/9/comment") return json(200, { ...submitted, admin_comment: "IT is on it" })
        if (url === "/api/v1/reports/9" && (init?.method ?? "GET") === "GET") return json(200, submitted)
        return json(200, [])
      })
      renderAt("/admin/reports")
      expect(await screen.findByText("Issues / remarks from the lead")).toBeInTheDocument()
      expect(screen.getByText(/Sent to admin .* by Priya Raman/)).toBeInTheDocument()
      expect(screen.queryByRole("button", { name: "Send to admin" })).not.toBeInTheDocument()
      await userEvent.type(screen.getByLabelText("Reply to the lead"), "IT is on it")
      await userEvent.click(screen.getByRole("button", { name: /Save reply/ }))
      await waitFor(() => expect(sent(fetchMock, "/api/v1/reports/9/comment")).toBe(true))
      expect(bodyOf(fetchMock, "/api/v1/reports/9/comment")).toEqual({ comment: "IT is on it" })
    })
  })
})
