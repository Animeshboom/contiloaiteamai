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

async function send(method: string, path: string, body?: BodyInit, json = false, query?: Query): Promise<Response> {
  const headers: Record<string, string> = {}
  if (json) headers["Content-Type"] = "application/json"
  if (token) headers.Authorization = `Bearer ${token}`
  try {
    return await fetch(buildUrl(path, query), { method, headers, body })
  } catch {
    throw new ApiError(0, "network", "Cannot reach the StudioTrack server. Is the API running?")
  }
}

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const res = await send(method, path, body === undefined ? undefined : JSON.stringify(body), body !== undefined, query)
  return parse<T>(res, path)
}

async function parse<T>(res: Response, path: string): Promise<T> {
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
  /** multipart upload of a single file under the field name "file" */
  upload: async <T>(path: string, file: File): Promise<T> => {
    const form = new FormData()
    form.append("file", file)
    return parse<T>(await send("POST", path, form), path)
  },
  /** authenticated download -> browser save dialog */
  download: async (path: string, filename: string): Promise<void> => {
    const res = await send("GET", path)
    if (!res.ok) await parse(res, path)
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong"
}
