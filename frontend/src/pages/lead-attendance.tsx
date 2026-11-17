import { useState, type FormEvent } from "react"
import { ChevronLeft, ChevronRight, PencilLine } from "lucide-react"

import { AttendanceTrendChart } from "@/components/charts"
import { AttendanceBadge, EmptyState, ErrorState, LoadingRows, PageHeader, StatCard } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Field, Input, NativeSelect, Textarea } from "@/components/ui/form-controls"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { addDays, formatDate, formatMinutes, formatTime, isoToStudioLocal, studioLocalToIso } from "@/lib/format"
import { useAction, useAttendanceSummary, useRoster } from "@/lib/queries"
import type { AttendanceStatus, RosterRow } from "@/lib/types"

export default function LeadAttendancePage() {
  const { config, user } = useAuth()
  const today = config?.studio_today ?? ""
  const [day, setDay] = useState(today)
  const [editing, setEditing] = useState<RosterRow | null>(null)
  const roster = useRoster({ on: day })
  const summary = useAttendanceSummary({ end: today })

  const counts = (roster.data ?? []).reduce<Record<string, number>>((acc, r) => ({ ...acc, [r.status]: (acc[r.status] ?? 0) + 1 }), {})

  return (
    <>
      <PageHeader
        title="Attendance"
        description="Team attendance by studio day. Corrections require a reason and are recorded in the audit log."
        actions={
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon" onClick={() => setDay(addDays(day, -1))} aria-label="Previous day"><ChevronLeft /></Button>
            <Input type="date" className="w-40" value={day} max={today} onChange={(e) => e.target.value && setDay(e.target.value)} aria-label="Date" />
            <Button variant="outline" size="icon" disabled={day >= today} onClick={() => setDay(addDays(day, 1))} aria-label="Next day"><ChevronRight /></Button>
            {day !== today && <Button variant="ghost" size="sm" onClick={() => setDay(today)}>Today</Button>}
          </div>
        }
      />

      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <StatCard label="Present" value={counts.present ?? 0} tone="green" />
          <StatCard label="Half day" value={counts.half_day ?? 0} />
          <StatCard label="Leave" value={counts.leave ?? 0} tone="blue" />
          <StatCard label="Absent" value={counts.absent ?? 0} tone={counts.absent ? "red" : "default"} />
          <StatCard label="Not checked in" value={counts.not_checked_in ?? 0} hint={day === today ? "Today only" : undefined} />
        </div>

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>{formatDate(day, true)}</CardTitle>
              <CardDescription>{user?.role === "admin" ? "All staff" : "Your team"}</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="px-2">
            {roster.error ? <ErrorState error={roster.error} onRetry={roster.refetch} /> : roster.isLoading ? <LoadingRows /> :
              !roster.data?.length ? <EmptyState title="No team members" description="Ask an admin to add artists to your team." /> : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead><TableHead>Status</TableHead><TableHead>In</TableHead><TableHead>Out</TableHead>
                      <TableHead>Worked</TableHead><TableHead>Note</TableHead><TableHead className="w-10" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {roster.data.map((r) => (
                      <TableRow key={r.user_id}>
                        <TableCell>
                          <div className="font-medium">{r.full_name}</div>
                          <div className="text-xs text-muted-foreground">{r.job_title ?? "—"}{user?.role === "admin" && r.team_name ? ` · ${r.team_name}` : ""}</div>
                        </TableCell>
                        <TableCell><AttendanceBadge status={r.status} /></TableCell>
                        <TableCell className="font-mono tabular">{formatTime(r.record?.check_in_at)}</TableCell>
                        <TableCell className="font-mono tabular">{formatTime(r.record?.check_out_at)}</TableCell>
                        <TableCell className="font-mono tabular">{formatMinutes(r.record?.worked_minutes)}</TableCell>
                        <TableCell className="max-w-[16rem] truncate text-xs text-muted-foreground" title={r.record?.notes ?? ""}>
                          {r.record?.corrected_at && <span className="mr-1 text-primary">Corrected ·</span>}{r.record?.notes ?? ""}
                        </TableCell>
                        <TableCell>
                          {r.user_id !== user?.id && (
                            <Button variant="ghost" size="icon" onClick={() => setEditing(r)} aria-label={`Correct attendance for ${r.full_name}`}><PencilLine /></Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Last 14 days</CardTitle><CardDescription>Headcount by status</CardDescription></CardHeader>
          <CardContent>{summary.data ? <AttendanceTrendChart data={summary.data} /> : <LoadingRows rows={3} />}</CardContent>
        </Card>
      </div>

      {editing && <CorrectionDialog row={editing} day={day} onClose={() => setEditing(null)} />}
    </>
  )
}

function CorrectionDialog({ row, day, onClose }: { row: RosterRow; day: string; onClose: () => void }) {
  const rec = row.record
  const [status, setStatus] = useState<AttendanceStatus>(rec?.status ?? "present")
  const [inAt, setInAt] = useState(rec?.check_in_at ? isoToStudioLocal(rec.check_in_at).slice(11) : "10:00")
  const [outAt, setOutAt] = useState(rec?.check_out_at ? isoToStudioLocal(rec.check_out_at).slice(11) : "")
  const [reason, setReason] = useState("")
  const needsTimes = status === "present" || status === "half_day"

  const save = useAction(
    () => api.put("/attendance/correct", {
      user_id: row.user_id, work_date: day, status, reason,
      check_in_at: needsTimes && inAt ? studioLocalToIso(`${day}T${inAt}`) : null,
      check_out_at: needsTimes && outAt ? studioLocalToIso(`${day}T${outAt}`) : null,
    }),
    { success: "Attendance updated", invalidate: [["attendance"], ["dashboard"]], onSuccess: onClose },
  )

  function submit(e: FormEvent) {
    e.preventDefault()
    save.mutate(undefined)
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Correct attendance</DialogTitle>
            <DialogDescription>{row.full_name} · {formatDate(day, true)}</DialogDescription>
          </DialogHeader>
          <Field label="Status" htmlFor="c-status">
            <NativeSelect id="c-status" value={status} onChange={(e) => setStatus(e.target.value as AttendanceStatus)}>
              <option value="present">Present</option>
              <option value="half_day">Half day</option>
              <option value="leave">Leave</option>
              <option value="absent">Absent</option>
            </NativeSelect>
          </Field>
          {needsTimes && (
            <div className="grid grid-cols-2 gap-3">
              <Field label="Check in (studio time)" htmlFor="c-in"><Input id="c-in" type="time" required value={inAt} onChange={(e) => setInAt(e.target.value)} /></Field>
              <Field label="Check out (optional)" htmlFor="c-out"><Input id="c-out" type="time" value={outAt} onChange={(e) => setOutAt(e.target.value)} /></Field>
            </div>
          )}
          <Field label="Reason for correction" htmlFor="c-reason" hint="Stored with the record and in the audit log.">
            <Textarea id="c-reason" required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Forgot to check in; confirmed on set" />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending}>Save correction</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
