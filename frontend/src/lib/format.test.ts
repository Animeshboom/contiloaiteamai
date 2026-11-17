import { afterEach, describe, expect, it } from "vitest"

import { addDays, formatDate, formatTime, isoToStudioLocal, relativeDeadline, setStudioTimezone, studioLocalToIso } from "./format"

afterEach(() => setStudioTimezone("UTC"))

describe("studio timezone conversion", () => {
  it("converts studio-local input to UTC for a fixed-offset zone (Asia/Kolkata, +05:30)", () => {
    setStudioTimezone("Asia/Kolkata")
    expect(studioLocalToIso("2026-11-18T19:00")).toBe("2026-11-18T13:30:00.000Z")
    expect(isoToStudioLocal("2026-11-18T13:30:00Z")).toBe("2026-11-18T19:00")
  })

  it("round-trips across a DST boundary (America/New_York)", () => {
    setStudioTimezone("America/New_York")
    // Before DST ends (EDT, -4) and after (EST, -5)
    expect(studioLocalToIso("2026-10-30T09:00")).toBe("2026-10-30T13:00:00.000Z")
    expect(studioLocalToIso("2026-11-02T09:00")).toBe("2026-11-02T14:00:00.000Z")
    for (const local of ["2026-03-10T08:15", "2026-07-04T23:59", "2026-12-31T00:00"]) {
      expect(isoToStudioLocal(studioLocalToIso(local))).toBe(local)
    }
  })

  it("renders times in the studio zone, not the browser's", () => {
    setStudioTimezone("Asia/Kolkata")
    expect(formatTime("2026-11-18T04:30:00Z")).toBe("10:00")
    setStudioTimezone("America/Los_Angeles")
    expect(formatTime("2026-11-18T04:30:00Z")).toBe("20:30")
  })
})

describe("date-only helpers", () => {
  it("formats work dates without timezone shifting", () => {
    setStudioTimezone("Pacific/Honolulu") // a zone that would shift a naive Date parse back a day
    expect(formatDate("2026-11-18")).toBe("18 Nov 2026")
  })

  it("adds days across month boundaries", () => {
    expect(addDays("2026-11-30", 1)).toBe("2026-12-01")
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28")
  })
})

describe("relativeDeadline", () => {
  it("flags overdue deadlines", () => {
    const past = new Date(Date.now() - 90 * 60000).toISOString()
    const future = new Date(Date.now() + 3 * 86400000 + 3600000).toISOString()
    expect(relativeDeadline(past)).toEqual({ text: "1h 30m overdue", overdue: true })
    expect(relativeDeadline(future).overdue).toBe(false)
    expect(relativeDeadline(future).text).toMatch(/^in 3d/)
  })
})
