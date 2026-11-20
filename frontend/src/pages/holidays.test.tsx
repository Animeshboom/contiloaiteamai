import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { Holiday } from "@/lib/types"
import HolidaysPage from "./holidays"

vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ config: { studio_today: "2026-11-19" } }) }))

const holidays: Holiday[] = [
  { id: 1, date: "2026-10-20", name: "Diwali", applies_to_all: true, teams: [] },
  { id: 2, date: "2026-12-05", name: "Team offsite", applies_to_all: false, teams: [{ id: 3, name: "Animation Unit" }, { id: 4, name: "VFX Unit" }] },
]

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }))

describe("HolidaysPage", () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock)
    fetchMock.mockImplementation((url: string) => (url.startsWith("/api/v1/holidays") ? json(200, holidays) : json(404, {})))
  })
  afterEach(() => { fetchMock.mockReset(); vi.unstubAllGlobals() })

  it("lists the year's holidays with 'Everyone' or the team names, dimming past days", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><HolidaysPage /></MemoryRouter>
      </QueryClientProvider>,
    )

    const diwali = (await screen.findByText("Diwali")).closest("tr")!
    expect(within(diwali).getByText("Everyone")).toBeInTheDocument()
    expect(diwali).toHaveClass("opacity-55")

    const trip = screen.getByText("Team offsite").closest("tr")!
    expect(within(trip).getByText("Animation Unit")).toBeInTheDocument()
    expect(within(trip).getByText("VFX Unit")).toBeInTheDocument()
    expect(within(trip).queryByText("Everyone")).not.toBeInTheDocument()
    expect(trip).not.toHaveClass("opacity-55")

    expect(fetchMock.mock.calls.some(([u]) => u === "/api/v1/holidays?year=2026")).toBe(true)
  })
})
