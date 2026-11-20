import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { Role, User } from "@/lib/types"
import EmployeesPage from "./employees"
import SettingsPage from "./settings"
import TwoStepPage from "./two-step"

const auth = vi.hoisted(() => ({
  role: "admin" as Role,
  mfaEnabled: false,
  setToken: vi.fn(),
  refreshUser: vi.fn(),
  logout: vi.fn(),
}))
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: { id: 1, role: auth.role, full_name: "Admin One", email: "admin@studio.test", team: null, mfa_enabled: auth.mfaEnabled },
    config: { studio_today: "2026-11-20", eod_deadline_hour: 19, email_provider: "mock", gmail_backend: "mock" },
    setToken: auth.setToken, refreshUser: auth.refreshUser, logout: auth.logout,
  }),
  useStudioDay: () => ["2026-11-20", () => {}, "2026-11-20"],
}))

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }))
const wrap = (ui: React.ReactNode, at = "/") => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[at]}>
      <Routes>
        <Route path="/admin" element={<div>Admin workspace</div>} />
        <Route path="*" element={ui} />
      </Routes>
    </MemoryRouter>
  </QueryClientProvider>
)
const posted = (fetchMock: ReturnType<typeof vi.fn>, url: string) =>
  fetchMock.mock.calls.filter(([u, i]) => u === url && i?.method === "POST")

const person = (over: Partial<User>): User => ({
  id: 5, email: "asha@studio.test", full_name: "Asha Rao", role: "artist", job_title: "Artist", team: { id: 1, name: "Animation Unit" },
  employee_code: null, phone: null, is_active: true, last_login_at: null, created_at: "2026-11-01T00:00:00Z",
  locked_until: null, mfa_enabled: false, ...over,
})

describe("security features", () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock)
    auth.role = "admin"
    auth.mfaEnabled = false
    auth.refreshUser.mockResolvedValue({ id: 1, role: "admin" })
  })
  afterEach(() => { fetchMock.mockReset(); vi.unstubAllGlobals(); vi.restoreAllMocks(); auth.setToken.mockReset(); auth.refreshUser.mockReset() })

  it("two-step setup shows the QR code and secret, and stores the new token on enable", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/v1/auth/mfa/setup") {
        return json(200, { secret: "JBSWY3DPEHPK3PXP", otpauth_uri: "otpauth://totp/StudioTrack:admin@studio.test?secret=JBSWY3DPEHPK3PXP&issuer=StudioTrack" })
      }
      if (url === "/api/v1/auth/mfa/enable") {
        return JSON.parse(String(init?.body)).code === "123456"
          ? json(200, { access_token: "aal2-tok", user: { id: 1, role: "admin", mfa_enabled: true } })
          : json(422, { error: "validation_failed", detail: "That code didn't match. Check the time on your phone and try again." })
      }
      return json(404, {})
    })
    render(wrap(<TwoStepPage />, "/admin/two-step"))

    expect(await screen.findByAltText("QR code for your authenticator app")).toHaveAttribute("src", expect.stringMatching(/^data:image\/svg\+xml/))
    expect(screen.getByTestId("mfa-secret")).toHaveTextContent("JBSW Y3DP EHPK 3PXP")
    expect(screen.getByText(/Google Authenticator/)).toBeInTheDocument()

    const input = screen.getByLabelText("Enter the 6-digit code from your authenticator app")
    await userEvent.type(input, "000000")
    await userEvent.click(screen.getByRole("button", { name: "Turn on two-step login" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("didn't match")
    expect(auth.setToken).not.toHaveBeenCalled()

    await userEvent.type(input, "123456")
    await userEvent.click(screen.getByRole("button", { name: "Turn on two-step login" }))
    expect(await screen.findByText("Admin workspace")).toBeInTheDocument()
    expect(auth.setToken).toHaveBeenCalledWith("aal2-tok")
    expect(auth.refreshUser).toHaveBeenCalled()
    expect(JSON.parse(String(posted(fetchMock, "/api/v1/auth/mfa/enable").at(-1)![1].body))).toEqual({ code: "123456" })
    expect(posted(fetchMock, "/api/v1/auth/mfa/setup")).toHaveLength(1)  // a second setup would replace the scanned secret
  })

  it("admin sees a locked account and unlocks it", async () => {
    const locked = person({ locked_until: "2099-01-01T00:00:00Z" })
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/v1/users/5/unlock" && init?.method === "POST") return json(200, { ...locked, locked_until: null })
      if (url.startsWith("/api/v1/users")) return json(200, [locked, person({ id: 6, full_name: "Ravi K", locked_until: "2020-01-01T00:00:00Z" })])
      return json(200, [])
    })
    render(wrap(<EmployeesPage />))

    expect(await screen.findByText("Asha Rao")).toBeInTheDocument()
    expect(screen.getAllByText("Locked")).toHaveLength(1)  // an expired lock doesn't count
    await userEvent.click(screen.getByRole("button", { name: "Actions for Asha Rao" }))
    await userEvent.click(await screen.findByRole("menuitem", { name: /Unlock/ }))
    await waitFor(() => expect(posted(fetchMock, "/api/v1/users/5/unlock")).toHaveLength(1))
  })

  it("admin resets another admin's two-step login after confirming", async () => {
    const other = person({ id: 7, full_name: "Second Admin", role: "admin", team: null, mfa_enabled: true })
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/v1/users/7/reset-two-step" && init?.method === "POST") return json(200, { ...other, mfa_enabled: false })
      if (url.startsWith("/api/v1/users")) return json(200, [other])
      return json(200, [])
    })
    render(wrap(<EmployeesPage />))

    await userEvent.click(await screen.findByRole("button", { name: "Actions for Second Admin" }))
    await userEvent.click(await screen.findByRole("menuitem", { name: /Reset two-step login/ }))
    expect(posted(fetchMock, "/api/v1/users/7/reset-two-step")).toHaveLength(0)
    await userEvent.click(await screen.findByRole("button", { name: "Reset two-step login" }))
    await waitFor(() => expect(posted(fetchMock, "/api/v1/users/7/reset-two-step")).toHaveLength(1))
  })

  it("team lead downloads a backup from Settings, and sees the rate-limit message", async () => {
    auth.role = "team_lead"
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() }))
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})
    let backups = 0
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/v1/backup") {
        backups += 1
        return backups === 1
          ? Promise.resolve(new Response("PK", { status: 200, headers: { "Content-Type": "application/zip" } }))
          : json(429, { error: "rate_limited", detail: "Too many backups. Try again later." })
      }
      return json(200, [])
    })
    render(wrap(<SettingsPage />))

    expect(screen.getByText("Saves a copy of your team's records to this computer. Keep it somewhere safe.")).toBeInTheDocument()
    expect(screen.queryByText(/Two-step login/)).not.toBeInTheDocument()  // admins only
    await userEvent.click(screen.getByRole("button", { name: /Download backup/ }))
    await waitFor(() => expect(click).toHaveBeenCalled())
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/backup", expect.objectContaining({ method: "GET" }))
    const anchor = click.mock.contexts[0] as HTMLAnchorElement
    expect(anchor.download).toBe("studiotrack-backup-2026-11-20.zip")

    await userEvent.click(screen.getByRole("button", { name: /Download backup/ }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many backups")
  })

  it("admin Settings shows the two-step status", async () => {
    fetchMock.mockImplementation(() => json(200, []))
    auth.mfaEnabled = true
    const { unmount } = render(wrap(<SettingsPage />))
    expect(screen.getByText(/Two-step login:/)).toHaveTextContent("On")
    unmount()

    auth.mfaEnabled = false
    render(wrap(<SettingsPage />))
    expect(screen.getByRole("link", { name: "Set up two-step login" })).toHaveAttribute("href", "/admin/two-step")
  })
})
