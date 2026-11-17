import { useEffect, useState } from "react"
import { LogIn, LogOut } from "lucide-react"

import { AttendanceBadge } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/misc"
import { api } from "@/lib/api"
import { formatDate, formatMinutes, formatTime, getStudioTimezone } from "@/lib/format"
import { keys, useAction, useToday } from "@/lib/queries"
import type { AttendanceRecord } from "@/lib/types"

function useClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 15_000)
    return () => clearInterval(t)
  }, [])
  return now
}

export function CheckInCard() {
  const { data, isLoading } = useToday()
  const now = useClock()
  const invalidate = [keys.today, ["attendance"], ["dashboard"]]
  const checkIn = useAction(() => api.post<AttendanceRecord>("/attendance/check-in"), {
    invalidate, success: (r) => `Checked in at ${formatTime(r.check_in_at)}`,
  })
  const checkOut = useAction(() => api.post<AttendanceRecord>("/attendance/check-out"), {
    invalidate, success: (r) => `Checked out at ${formatTime(r.check_out_at)} · ${formatMinutes(r.worked_minutes)}`,
  })

  if (isLoading || !data) return <Skeleton className="h-36" />
  const rec = data.record
  const clock = new Intl.DateTimeFormat("en-GB", { timeZone: getStudioTimezone(), hour: "2-digit", minute: "2-digit", hour12: false }).format(now)
  const liveMinutes = rec?.check_in_at && !rec.check_out_at ? Math.floor((now.getTime() - new Date(rec.check_in_at).getTime()) / 60000) : null

  return (
    <Card className="relative overflow-hidden p-5">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">{formatDate(data.work_date, true)}</div>
          <div className="mt-1 font-mono text-4xl font-medium tabular">{clock}</div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {rec ? <AttendanceBadge status={rec.status} /> : <AttendanceBadge status="not_checked_in" />}
            {rec?.check_in_at && <span>In {formatTime(rec.check_in_at)}</span>}
            {rec?.check_out_at && <span>· Out {formatTime(rec.check_out_at)} · {formatMinutes(rec.worked_minutes)}</span>}
            {liveMinutes !== null && <span>· {formatMinutes(liveMinutes)} so far</span>}
          </div>
        </div>
        <div className="flex gap-2">
          <Button size="lg" disabled={!data.can_check_in} loading={checkIn.isPending} onClick={() => checkIn.mutate(undefined)}>
            <LogIn />Check in
          </Button>
          <Button size="lg" variant="outline" disabled={!data.can_check_out} loading={checkOut.isPending} onClick={() => checkOut.mutate(undefined)}>
            <LogOut />Check out
          </Button>
        </div>
      </div>
      {rec && (rec.status === "leave" || rec.status === "absent") && (
        <p className="mt-4 rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
          Today is recorded as {rec.status} by your team lead{rec.notes ? `: “${rec.notes}”` : ""}.
        </p>
      )}
    </Card>
  )
}
