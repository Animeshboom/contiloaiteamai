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
    await userEvent.type(screen.getByLabelText("Email"), lead.email)
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
    await userEvent.type(screen.getByLabelText("Email"), "x@studio.test")
    await userEvent.type(screen.getByLabelText("Password"), "wrong")
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password")
    expect(localStorage.getItem("studiotrack.token")).toBeNull()
  })

  it("explains when the API is unreachable", async () => {
    fetchMock.mockImplementation(() => Promise.reject(new TypeError("Failed to fetch")))
    renderLogin()
    await userEvent.type(screen.getByLabelText("Email"), lead.email)
    await userEvent.type(screen.getByLabelText("Password"), "x")
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }))
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/Cannot reach the StudioTrack server/))
  })
})
