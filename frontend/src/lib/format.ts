/** Display helpers. All timestamps are rendered in the studio timezone, never the browser's. */

let studioTz = "UTC"

export function setStudioTimezone(tz: string) {
  studioTz = tz
}

export function getStudioTimezone() {
  return studioTz
}

/** Today's date (YYYY-MM-DD) in the studio timezone, from the browser clock. */
export function studioTodayNow(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: studioTz, year: "numeric", month: "2-digit", day: "2-digit" }).format(now)
}

/** Default deadline for a new assignment: today's EOD, or tomorrow's once today's has passed. */
export function nextEodLocal(today: string, eodHour: number, now: Date = new Date()): string {
  const at = (d: string) => `${d}T${String(eodHour).padStart(2, "0")}:00`
  return new Date(studioLocalToIso(at(today))) > now ? at(today) : at(addDays(today, 1))
}

function fmt(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions): string {
  if (!iso) return "—"
  return new Intl.DateTimeFormat("en-GB", { timeZone: studioTz, ...opts }).format(new Date(iso))
}

export const formatTime = (iso?: string | null) => fmt(iso, { hour: "2-digit", minute: "2-digit", hour12: false })
export const formatCurrentStudioTime = () =>
  new Intl.DateTimeFormat("en-GB", { timeZone: studioTz, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date())
export const formatDateTime = (iso?: string | null) =>
  fmt(iso, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false })

/** For date-only values (YYYY-MM-DD): format without timezone shifting. */
export function formatDate(d?: string | null, withWeekday = false): string {
  if (!d) return "—"
  const [y, m, day] = d.split("-").map(Number)
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC", day: "2-digit", month: "short", year: "numeric", ...(withWeekday ? { weekday: "short" } : {}),
  }).format(new Date(Date.UTC(y, m - 1, day)))
}

/** "Mon, 24 Nov 2026" for one day, "24 Nov 2026 – 26 Nov 2026" for a range. */
export function formatDateRange(start: string, end: string): string {
  return start === end ? formatDate(start, true) : `${formatDate(start)} – ${formatDate(end)}`
}

export function shortDay(d: string): string {
  const [y, m, day] = d.split("-").map(Number)
  return new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", weekday: "short", day: "2-digit" }).format(new Date(Date.UTC(y, m - 1, day)))
}

export function formatMinutes(min: number | null | undefined): string {
  if (min == null) return "—"
  const h = Math.floor(min / 60)
  const m = min % 60
  return `${h}h ${m.toString().padStart(2, "0")}m`
}

/** "in 3h 20m" / "2h 05m overdue" relative to now. */
export function relativeDeadline(iso: string): { text: string; overdue: boolean } {
  const diffMin = Math.round((new Date(iso).getTime() - Date.now()) / 60000)
  const abs = Math.abs(diffMin)
  const days = Math.floor(abs / 1440)
  const text = days >= 1 ? `${days}d ${Math.floor((abs % 1440) / 60)}h` : formatMinutes(abs)
  return diffMin < 0 ? { text: `${text} overdue`, overdue: true } : { text: `in ${text}`, overdue: false }
}

/** Convert a studio-local "YYYY-MM-DDTHH:mm" (from <input type=datetime-local>) to an ISO UTC string. */
export function studioLocalToIso(local: string): string {
  const [datePart, timePart] = local.split("T")
  const [y, m, d] = datePart.split("-").map(Number)
  const [hh, mm] = timePart.split(":").map(Number)
  // Find the UTC instant whose studio-local rendering equals the input (handles any offset).
  const guess = Date.UTC(y, m - 1, d, hh, mm)
  const offset = tzOffsetMinutes(new Date(guess))
  let ts = guess - offset * 60000
  const offset2 = tzOffsetMinutes(new Date(ts))
  if (offset2 !== offset) ts = guess - offset2 * 60000
  return new Date(ts).toISOString()
}

/** ISO UTC -> studio-local "YYYY-MM-DDTHH:mm" for datetime-local inputs. */
export function isoToStudioLocal(iso: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: studioTz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(new Date(iso))
  const g = (t: string) => parts.find((p) => p.type === t)?.value ?? "00"
  return `${g("year")}-${g("month")}-${g("day")}T${g("hour") === "24" ? "00" : g("hour")}:${g("minute")}`
}

function tzOffsetMinutes(date: Date): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: studioTz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).formatToParts(date)
  const g = (t: string) => Number(parts.find((p) => p.type === t)?.value)
  const asUtc = Date.UTC(g("year"), g("month") - 1, g("day"), g("hour") % 24, g("minute"), g("second"))
  return Math.round((asUtc - date.getTime()) / 60000)
}

export function addDays(d: string, n: number): string {
  const [y, m, day] = d.split("-").map(Number)
  const dt = new Date(Date.UTC(y, m - 1, day + n))
  return dt.toISOString().slice(0, 10)
}

export const titleCase = (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())

export function initials(name: string): string {
  return name.replace(/\(.*?\)/g, "").trim().split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? "").join("")
}
