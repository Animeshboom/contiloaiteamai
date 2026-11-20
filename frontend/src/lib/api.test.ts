import { afterEach, expect, test, vi } from "vitest"

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.resetModules()
})

async function firstRequestUrl(base: string | undefined) {
  if (base !== undefined) vi.stubEnv("VITE_API_BASE_URL", base)
  vi.resetModules()
  const { api } = await import("./api")
  const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }))
  vi.stubGlobal("fetch", fetchMock)
  await api.get("/auth/me", { page: 2, empty: "" })
  return fetchMock.mock.calls[0][0]
}

test("same-origin /api by default (dev proxy, Docker nginx)", async () => {
  expect(await firstRequestUrl(undefined)).toBe("/api/v1/auth/me?page=2")
})

test("prefixes the configured API origin for hosted builds", async () => {
  expect(await firstRequestUrl("https://studiotrack-api.onrender.com/")).toBe(
    "https://studiotrack-api.onrender.com/api/v1/auth/me?page=2",
  )
})
