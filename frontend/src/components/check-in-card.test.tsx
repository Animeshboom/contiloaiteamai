import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { CheckInCard } from "./check-in-card"

const cfg = vi.hoisted(() => ({ show: false }))
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ user: { id: 3, role: "artist" }, config: { studio_today: "2026-11-20", show_checkin_times: cfg.show } }),
}))

const today = {
  work_date: "2026-11-20", can_check_in: false, can_check_out: false,
  record: {
    id: 1, user_id: 3, work_date: "2026-11-20", status: "present", check_in_at: "2026-11-20T04:32:00Z", check_out_at: "2026-11-20T12:47:00Z",
    worked_minutes: 495, notes: null, work_note: null, corrected_by_id: null, corrected_at: null,
  },
}

describe("CheckInCard", () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock)
    fetchMock.mockImplementation(() => Promise.resolve(new Response(JSON.stringify(today), { status: 200, headers: { "Content-Type": "application/json" } })))
  })
  afterEach(() => { fetchMock.mockReset(); vi.unstubAllGlobals() })

  const renderCard = () => render(<QueryClientProvider client={new QueryClient()}><CheckInCard /></QueryClientProvider>)

  it("hides check-in and check-out times when the studio turned them off", async () => {
    cfg.show = false
    renderCard()
    expect(await screen.findByText("Present")).toBeInTheDocument()
    expect(screen.queryByText(/^In /)).not.toBeInTheDocument()
    expect(screen.queryByText(/Out /)).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Check in/ })).toBeInTheDocument()
  })

  it("shows the times when show_checkin_times is on", async () => {
    cfg.show = true
    renderCard()
    expect(await screen.findByText(/^In \d\d:\d\d/)).toBeInTheDocument()
    expect(screen.getByText(/Out \d\d:\d\d/)).toBeInTheDocument()
  })
})
