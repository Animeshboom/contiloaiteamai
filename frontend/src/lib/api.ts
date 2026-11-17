/** Thin fetch wrapper: JSON in/out, bearer token, uniform errors. */

const TOKEN_KEY = "studiotrack.token"

export class ApiError extends Error {
  status: number
  code: string
  fieldErrors: { field: string; message: string }[]
  constructor(status: number, code: string, message: string, fieldErrors: { field: string; message: string }[] = []) {
    super(message)
    this.status = status
    this.code = code
    this.fieldErrors = fieldErrors
  }
}

let token: string | null = localStorage.getItem(TOKEN_KEY)
let onUnauthorized: (() => void) | null = null

export const auth = {
  get token() {
    return token
  },
  set(t: string | null) {
    token = t
    if (t) localStorage.setItem(TOKEN_KEY, t)
    else localStorage.removeItem(TOKEN_KEY)
  },
  onUnauthorized(cb: () => void) {
    onUnauthorized = cb
  },
}

type Query = Record<string, string | number | boolean | null | undefined>

function buildUrl(path: string, query?: Query) {
  const url = new URL(`/api/v1${path}`, window.location.origin)
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v))
    }
  }
  return url.pathname + url.search
}

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers["Content-Type"] = "application/json"
  if (token) headers.Authorization = `Bearer ${token}`

  let res: Response
  try {
    res = await fetch(buildUrl(path, query), { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  } catch {
    throw new ApiError(0, "network", "Cannot reach the StudioTrack server. Is the API running?")
  }

  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    if (res.status === 401 && path !== "/auth/login") onUnauthorized?.()
    const fieldErrors = Array.isArray(data.errors) ? data.errors : []
    const message =
      fieldErrors.length > 0
        ? fieldErrors.map((e: { field: string; message: string }) => `${e.field ? e.field + ": " : ""}${e.message.replace(/^Value error, /, "")}`).join("; ")
        : data.detail ?? `Request failed (${res.status})`
    throw new ApiError(res.status, data.error ?? "error", message, fieldErrors)
  }
  return data as T
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>("GET", path, undefined, query),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body ?? {}),
  del: <T = void>(path: string) => request<T>("DELETE", path),
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong"
}
