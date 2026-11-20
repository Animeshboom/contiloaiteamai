import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { StaffAttendanceExport } from "./attendance-export"

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ user: { id: 1, role: "admin" }, config: { studio_today: "2026-11-20" } }),
}))

describe("StaffAttendanceExport", () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock)
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() }))
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {}) // jsdom can't navigate to the blob
    fetchMock.mockImplementation((url: string) => {
      if (url.startsWith("/api/v1/teams")) {
        return Promise.resolve(new Response(JSON.stringify([{ id: 2, name: "Animation Unit" }]), { status: 200, headers: { "Content-Type": "application/json" } }))
      }
      return Promise.resolve(new Response("Name,Email\n", { status: 200, headers: { "Content-Type": "text/csv" } }))
    })
  })
  afterEach(() => { fetchMock.mockReset(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it("downloads the chosen month and team with the auth'd helper", async () => {
    render(<QueryClientProvider client={new QueryClient()}><StaffAttendanceExport /></QueryClientProvider>)

    expect(screen.getByLabelText("Export month")).toHaveValue("2026-11")
    await screen.findByRole("option", { name: "Animation Unit" })
    await userEvent.selectOptions(screen.getByLabelText("Export team"), "2")
    await userEvent.click(screen.getByRole("button", { name: /Download CSV/ }))

    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).startsWith("/api/v1/attendance/export"))).toBe(true))
    const [url] = fetchMock.mock.calls.find(([u]) => String(u).startsWith("/api/v1/attendance/export"))!
    expect(url).toBe("/api/v1/attendance/export?month=2026-11&team_id=2")
  })
})
