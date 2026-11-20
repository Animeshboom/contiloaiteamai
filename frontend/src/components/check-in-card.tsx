import { useEffect, useState, type FormEvent } from "react"
import { LogIn, LogOut } from "lucide-react"

import { AttendanceBadge } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Field, Textarea } from "@/components/ui/form-controls"
import { Skeleton } from "@/components/ui/misc"
import { api } from "@/lib/api"
import { formatDate, formatMinutes, formatTime, getStudioTimezone } from "@/lib/format"
import { keys, useAction, useShowCheckinTimes, useToday } from "@/lib/queries"
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
  const showTimes = useShowCheckinTimes()
  const invalidate = [keys.today, ["attendance"], ["dashboard"]]
  const checkIn = useAction(() => api.post<AttendanceRecord>("/attendance/check-in"), {
    invalidate, success: (r) => (showTimes ? `Checked in at ${formatTime(r.check_in_at)}` : "Checked in"),
  })
  const [outOpen, setOutOpen] = useState(false)
  const [note, setNote] = useState("")
  const checkOut = useAction(
    () => api.post<AttendanceRecord>("/attendance/check-out", note.trim() ? { note: note.trim() } : {}),
    {
      invalidate, success: (r) => (showTimes ? `Checked out at ${formatTime(r.check_out_at)} · ${formatMinutes(r.worked_minutes)}` : "Checked out"),
      onSuccess: () => { setOutOpen(false); setNote("") },
    },
  )
  const submitOut = (e: FormEvent) => { e.preventDefault(); checkOut.mutate(undefined) }

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
            {showTimes && rec?.check_in_at && <span>In {formatTime(rec.check_in_at)}</span>}
            {showTimes && rec?.check_out_at && <span>· Out {formatTime(rec.check_out_at)} · {formatMinutes(rec.worked_minutes)}</span>}
            {showTimes && liveMinutes !== null && <span>· {formatMinutes(liveMinutes)} so far</span>}
            {!showTimes && rec?.check_out_at && rec.worked_minutes != null && <span>{formatMinutes(rec.worked_minutes)} worked</span>}
          </div>
        </div>
        <div className="flex gap-2">
          <Button size="lg" disabled={!data.can_check_in} loading={checkIn.isPending} onClick={() => checkIn.mutate(undefined)}>
            <LogIn />Check in
          </Button>
          <Button size="lg" variant="outline" disabled={!data.can_check_out || checkOut.isPending} onClick={() => setOutOpen(true)}>
            <LogOut />Check out
          </Button>
        </div>
      </div>
      {rec && (rec.status === "leave" || rec.status === "absent") && (
        <p className="mt-4 rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
          Today is recorded as {rec.status}{rec.notes ? `: “${rec.notes}”` : ""}.
        </p>
      )}
      {rec?.work_note && <p className="mt-4 whitespace-pre-line rounded-md border bg-background/40 px-3 py-2 text-xs text-muted-foreground">Your note: {rec.work_note}</p>}
      <Dialog open={outOpen} onOpenChange={setOutOpen}>
        <DialogContent>
          <form onSubmit={submitOut} className="grid gap-4">
            <DialogHeader>
              <DialogTitle>Check out</DialogTitle>
              <DialogDescription>Optional: a short note for your lead's day report.</DialogDescription>
            </DialogHeader>
            <Field label="What did you do today? Any blockers?" htmlFor="co-note">
              <Textarea id="co-note" rows={4} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)}
                placeholder="e.g. Finished SC03 lighting; waiting on the client's music for SC04." />
            </Field>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOutOpen(false)}>Cancel</Button>
              <Button type="submit" loading={checkOut.isPending}><LogOut />Check out</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
