import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { ActivityEntry } from "@/lib/types"
import ActivityPage from "./activity"

const entry = (id: number, summary: string): ActivityEntry => ({
  id, at: "2026-11-20T04:00:00Z", actor_id: 2, actor: "Priya Raman", action: "attendance.correct", summary,
  subject: "Asha Rao", details: { status: "present", reason: "Was in class" }, ip: "10.0.0.5",
})

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }))

describe("ActivityPage", () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock)
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} })
    // First page is full (100 rows) so "Load more" shows; the second page is short so it disappears.
    const first = Array.from({ length: 100 }, (_, i) => entry(500 - i, i === 0 ? "corrected attendance — Asha Rao (“Was in class”)" : `event ${500 - i}`))
    fetchMock.mockImplementation((url: string) => {
      if (url.startsWith("/api/v1/activity")) return json(200, url.includes("before_id=") ? [entry(300, "created team Animation Unit")] : first)
      return json(200, [])
    })
  })
  afterEach(() => { fetchMock.mockReset(); vi.unstubAllGlobals() })

  it("renders rows, expands details, and loads older entries with before_id", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><ActivityPage /></MemoryRouter>
      </QueryClientProvider>,
    )

    const summary = await screen.findByText("corrected attendance — Asha Rao (“Was in class”)")
    expect(screen.getAllByText("Priya Raman").length).toBeGreaterThan(0)
    expect(fetchMock.mock.calls.some(([u]) => u === "/api/v1/activity?limit=100")).toBe(true)

    await userEvent.click(summary)
    expect(screen.getByText("10.0.0.5")).toBeInTheDocument()
    expect(screen.getByText(/"reason": "Was in class"/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: "Load more" }))
    expect(await screen.findByText("created team Animation Unit")).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([u]) => u === "/api/v1/activity?limit=100&before_id=401")).toBe(true)
    await waitFor(() => expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument())
  })
})
