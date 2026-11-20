import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AuthProvider } from "@/lib/auth-context"
import LoginPage from "./login"

const lead = {
  id: 2, email: "lead.anim@studio.test", full_name: "Priya Raman", role: "team_lead",
  job_title: "Animation Lead", team: { id: 1, name: "Animation Unit" }, is_active: true,
  last_login_at: null, created_at: "2026-11-01T00:00:00Z",
}
const config = { studio_timezone: "Asia/Kolkata", eod_deadline_hour: 19, studio_today: "2026-11-18", email_provider: "mock", gmail_backend: "mock", ai_enabled: false, max_upload_mb: 25 }

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }))
}

function renderLogin() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/login"]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/lead" element={<div>Lead workspace</div>} />
            <Route path="/admin" element={<div>Admin workspace</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("LoginPage", () => {
  const fetchMock = vi.fn()
  beforeEach(() => vi.stubGlobal("fetch", fetchMock))
  afterEach(() => { fetchMock.mockReset(); vi.unstubAllGlobals() })

  it("signs a team lead in and routes to the lead workspace", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith("/auth/login")) return json(200, { access_token: "tok", token_type: "bearer", expires_in: 3600, user: lead })
      if (url.endsWith("/auth/me")) return json(200, lead)
      if (url.endsWith("/meta/config")) return json(200, config)
      return json(404, {})
    })
    renderLogin()
    await userEvent.type(screen.getByLabelText("Email or Employee ID"), lead.email)
    await userEvent.type(screen.getByLabelText("Password"), "Lead@12345")
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }))

    expect(await screen.findByText("Lead workspace")).toBeInTheDocument()
    expect(localStorage.getItem("studiotrack.token")).toBe("tok")
    const [, init] = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/auth/me"))!
    expect(init.headers.Authorization).toBe("Bearer tok")
  })

  it("shows the server's error and stores no token on bad credentials", async () => {
    fetchMock.mockImplementation(() => json(401, { error: "unauthorized", detail: "Invalid email or password" }))
    renderLogin()
    await userEvent.type(screen.getByLabelText("Email or Employee ID"), "x@studio.test")
    await userEvent.type(screen.getByLabelText("Password"), "wrong")
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password")
    expect(localStorage.getItem("studiotrack.token")).toBeNull()
  })

  it("asks an admin with two-step login for the code, then signs in", async () => {
    const admin = { ...lead, id: 1, email: "admin@studio.test", role: "admin", team: null, mfa_enabled: true, locked_until: null }
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/login")) return json(200, { access_token: null, mfa_required: true, mfa_token: "ticket", user: admin })
      if (url.endsWith("/auth/login/mfa")) {
        return JSON.parse(String(init?.body)).code === "123456"
          ? json(200, { access_token: "aal2-tok", user: admin })
          : json(401, { error: "unauthorized", detail: "Wrong code. Check the time on your phone and try again." })
      }
      if (url.endsWith("/auth/me")) return json(200, admin)
      if (url.endsWith("/meta/config")) return json(200, config)
      return json(404, {})
    })
    renderLogin()
    await userEvent.type(screen.getByLabelText("Email or Employee ID"), admin.email)
    await userEvent.type(screen.getByLabelText("Password"), "Admin@12345")
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }))

    const codeInput = await screen.findByLabelText("Enter the 6-digit code from your authenticator app")
    expect(codeInput).toHaveAttribute("autocomplete", "one-time-code")
    expect(codeInput).toHaveAttribute("inputmode", "numeric")
    expect(localStorage.getItem("studiotrack.token")).toBeNull()

    await userEvent.type(codeInput, "000000")
    await userEvent.click(screen.getByRole("button", { name: "Verify" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong code")
    expect(screen.getByLabelText("Enter the 6-digit code from your authenticator app")).toBeInTheDocument()  // can retry

    await userEvent.type(screen.getByLabelText("Enter the 6-digit code from your authenticator app"), "123456")
    await userEvent.click(screen.getByRole("button", { name: "Verify" }))
    expect(await screen.findByText("Admin workspace")).toBeInTheDocument()
    const bodies = fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/auth/login/mfa")).map(([, i]) => JSON.parse(String(i.body)))
    expect(bodies.at(-1)).toEqual({ mfa_token: "ticket", code: "123456" })
    expect(localStorage.getItem("studiotrack.token")).toBe("aal2-tok")
  })

  it("sends the admin back to the password step when the sign-in ticket expired", async () => {
    const admin = { ...lead, id: 1, role: "admin", mfa_enabled: true }
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith("/auth/login")) return json(200, { access_token: null, mfa_required: true, mfa_token: "old", user: admin })
      if (url.endsWith("/auth/login/mfa")) return json(401, { error: "unauthorized", detail: "The sign-in took too long. Start again." })
      return json(404, {})
    })
    renderLogin()
    await userEvent.type(screen.getByLabelText("Email or Employee ID"), "admin@studio.test")
    await userEvent.type(screen.getByLabelText("Password"), "Admin@12345")
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }))
    await userEvent.type(await screen.findByLabelText("Enter the 6-digit code from your authenticator app"), "123456")
    await userEvent.click(screen.getByRole("button", { name: "Verify" }))

    expect(await screen.findByLabelText("Password")).toBeInTheDocument()
    expect(screen.getByRole("alert")).toHaveTextContent("took too long")
  })

  it("shows the lockout message after too many wrong passwords", async () => {
    const msg = "Too many wrong passwords. Try again in 15 minute(s) or ask your administrator."
    fetchMock.mockImplementation(() => json(429, { error: "account_locked", detail: msg }))
    renderLogin()
    await userEvent.type(screen.getByLabelText("Email or Employee ID"), lead.email)
    await userEvent.type(screen.getByLabelText("Password"), "wrong")
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }))

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("Account locked")
    expect(alert).toHaveTextContent(msg)
    expect(screen.getByLabelText("Password")).toBeInTheDocument()
    expect(localStorage.getItem("studiotrack.token")).toBeNull()
  })

  it("explains when the API is unreachable", async () => {
    fetchMock.mockImplementation(() => Promise.reject(new TypeError("Failed to fetch")))
    renderLogin()
    await userEvent.type(screen.getByLabelText("Email or Employee ID"), lead.email)
    await userEvent.type(screen.getByLabelText("Password"), "x")
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }))
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/Cannot reach the StudioTrack server/))
  })
})
