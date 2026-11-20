import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { Submission } from "@/lib/types"
import ReviewsPage from "./reviews"

const sub: Submission = {
  id: 7, assignment_id: 3, assignment_title: "EP01 Pilot — Scenes 01, 02", project_id: 1, project_title: "Neon", project_code: "NEON-01",
  episode_number: 1, episode_title: "Pilot", artist_id: 4, artist_name: "Arjun Mehta (Demo Artist)", revision_number: 1,
  previous_submission_id: null, is_resubmission: false, submitted_at: "2026-11-18T10:00:00Z", submission_date: "2026-11-18",
  is_late: false, deadline: "2026-11-18T13:30:00Z", scenes_completed_count: 2, work_description: "Rendered",
  output_links: ["https://drive.example.com/x"], comments: null, status: "pending_review",
  deliverables: [
    { id: 1, scene_id: 11, label: "EP01 SC01", status: "submitted", approved_at: null, approved_by_name: null },
    { id: 2, scene_id: 12, label: "EP01 SC02", status: "submitted", approved_at: null, approved_by_name: null },
  ],
  attachments: [], reviews: [],
}

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }))

describe("ReviewsPage", () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock)
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/review") && init?.method === "POST") return json(200, { ...sub, status: "rejected" })
      if (url.startsWith("/api/v1/submissions")) return json(200, [sub])
      return json(404, {})
    })
  })
  afterEach(() => { fetchMock.mockReset(); vi.unstubAllGlobals() })

  function renderPage() {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><ReviewsPage /></MemoryRouter>
      </QueryClientProvider>,
    )
  }

  it("requires feedback for partial approval and sends only the checked scenes", async () => {
    renderPage()
    const approveAll = await screen.findByRole("button", { name: /^Approve$/ })
    expect(approveAll).toBeEnabled()
    expect(screen.getByRole("button", { name: /Request revision/ })).toBeDisabled() // no feedback yet

    await userEvent.click(screen.getByRole("checkbox", { name: /EP01 SC02/ }))
    const partial = screen.getByRole("button", { name: /Approve 1 of 2/ })
    expect(partial).toBeDisabled()
    expect(screen.getByText(/Explain what needs revising/)).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText("Feedback for the assignee"), "SC02 flickers at 00:04")
    expect(partial).toBeEnabled()
    await userEvent.click(partial)

    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/submissions/7/review"))).toBe(true))
    const [, init] = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/submissions/7/review"))!
    expect(JSON.parse(init.body)).toEqual({ decision: "approved", feedback: "SC02 flickers at 00:04", approved_scene_ids: [11] })
  })

  it("shows an empty state when nothing is pending", async () => {
    fetchMock.mockImplementation(() => json(200, []))
    renderPage()
    expect(await screen.findByText("Review queue is empty")).toBeInTheDocument()
  })
})
