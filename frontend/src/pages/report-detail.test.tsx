import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { Report } from "@/lib/types"
import ReportDetailPage from "./report-detail"

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ user: { role: "team_lead" }, config: { email_provider: "mcp", gmail_backend: "mock" } }),
}))

const totals = {
  team_members: 4, present: 1, half_day: 0, on_leave: 1, absent: 0, not_checked_in: 2, attendance_rate_pct: 25,
  projects_worked_on: 1, assignments_distributed: 2, assignments_active: 2, scenes_assigned: 4, scenes_submitted: 3,
  deliverables_submitted: 3, submissions: 2, scenes_approved: 1, scenes_rejected: 1, approval_rate_pct: 50,
  pending_reviews: 1, incomplete_assignments: 2, delayed_assignments: 1, late_submissions: 0,
}
const report: Report = {
  id: 9, report_date: "2026-11-18", status: "draft", subject: "Daily production report", recipients: ["producer@studio.test"],
  ai_status: "generated", created_by_name: "Priya", created_at: "2026-11-18T12:00:00Z", approved_at: null, sent_at: null,
  sent_by_name: null, delivery_status: null, filters: {}, ai_note: null, approved_by_name: null, gmail_message_id: null,
  gmail_draft_id: null, email_error: null, body: "SUMMARY\n1 of 4 team members were present.",
  narrative: { summary: "x", highlights: [], concerns: [] },
  metrics: { report_date: "2026-11-18", generated_at: "", as_of: "end of day", scope: { teams: [], filters: {} }, totals,
    attendance_by_status: {}, projects: [], artists: [], incomplete_assignments: [], delayed_assignments: [], remarks: [] },
}
const recipients = [
  { id: 1, email: "producer@studio.test", name: "Producer", purpose: "eod_report", is_active: true },
  { id: 2, email: "studio.head@studio.test", name: "Studio Head", purpose: "eod_report", is_active: true },
]
const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }))

describe("ReportDetailPage", () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock)
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET"
      if (url === "/api/v1/recipients") return json(200, recipients)
      if (url === "/api/v1/reports/9" && method === "GET") return json(200, report)
      if (url === "/api/v1/reports/9" && method === "PATCH") return json(200, report)
      if (url.endsWith("/approve")) return json(200, { ...report, status: "approved" })
      if (url.endsWith("/send")) return json(200, { ...report, status: "sent", delivery_status: "sent", recipients: JSON.parse(String(fetchMock.mock.calls.find(([u]) => String(u).endsWith("/approve"))![1].body)).recipients })
      return json(404, {})
    })
  })
  afterEach(() => { fetchMock.mockReset(); vi.unstubAllGlobals() })

  it("approves exactly the edited text and recipients, then sends — only after confirmation", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={["/lead/reports/9"]}>
          <Routes><Route path="/lead/reports/:id" element={<ReportDetailPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    const body = await screen.findByLabelText("Body (plain text)")
    await userEvent.type(body, "\nLead note.")
    await userEvent.click(screen.getByRole("checkbox", { name: /Studio Head/ }))

    await userEvent.click(screen.getByRole("button", { name: /Approve & send/ }))
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/send"))).toBe(false) // nothing sent before confirming
    expect(screen.getByText(/You are approving exactly this text and recipient list/)).toBeInTheDocument()

    await userEvent.click(screen.getAllByRole("button", { name: "Approve & send" }).at(-1)!)
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/send"))).toBe(true))

    const writes = fetchMock.mock.calls.filter(([, i]) => i?.method && i.method !== "GET").map(([u, i]) => [String(u), i.method])
    expect(writes).toEqual([["/api/v1/reports/9", "PATCH"], ["/api/v1/reports/9/approve", "POST"], ["/api/v1/reports/9/send", "POST"]])
    const patch = JSON.parse(String(fetchMock.mock.calls.find(([, i]) => i?.method === "PATCH")![1].body))
    expect(patch.body).toContain("Lead note.")
    const approve = JSON.parse(String(fetchMock.mock.calls.find(([u]) => String(u).endsWith("/approve"))![1].body))
    expect(approve.recipients.sort()).toEqual(["producer@studio.test", "studio.head@studio.test"])
  })
})
