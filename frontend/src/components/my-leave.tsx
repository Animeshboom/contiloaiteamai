import { useState, type FormEvent } from "react"
import { CalendarPlus } from "lucide-react"

import { ErrorState, LeaveStatusBadge } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Field, Input, Textarea } from "@/components/ui/form-controls"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { formatDateRange } from "@/lib/format"
import { LEAVE_KEYS, useAction, useMyLeave } from "@/lib/queries"
import type { Leave } from "@/lib/types"
import { cn } from "@/lib/utils"

/** Request leave + my requests (artists and leads). Leads' requests are decided by an admin. */
export function MyLeaveCard() {
  const { user } = useAuth()
  const { data, error, refetch } = useMyLeave()
  const [open, setOpen] = useState(false)
  const cancel = useAction((id: number) => api.post<Leave>(`/me/leave/${id}/cancel`), { success: "Leave request cancelled", invalidate: LEAVE_KEYS })

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
        <div>
          <CardTitle>My leave</CardTitle>
          <CardDescription>{user?.role === "team_lead" ? "An administrator approves your requests." : "Your team lead approves your requests."}</CardDescription>
        </div>
        <Button variant="outline" onClick={() => setOpen(true)}><CalendarPlus />Request leave</Button>
      </CardHeader>
      <CardContent>
        {error ? <ErrorState error={error} onRetry={refetch} /> : !data?.length ? <p className="text-sm text-muted-foreground">No leave requests yet.</p> : (
          <ul className="divide-y">
            {data.map((l) => (
              <li key={l.id} className="flex flex-wrap items-start justify-between gap-2 py-2.5">
                <div className="min-w-0 space-y-0.5">
                  <div className="text-sm font-medium">{formatDateRange(l.start, l.end)} <span className="font-normal text-muted-foreground">· {l.days} day{l.days === 1 ? "" : "s"}</span></div>
                  <div className="text-xs text-muted-foreground">{l.reason}</div>
                  {l.decision_note && (
                    <div className={cn("text-xs", l.status === "rejected" ? "text-destructive" : "text-muted-foreground")}>
                      {l.decided_by ? `${l.decided_by}: ` : ""}{l.decision_note}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <LeaveStatusBadge status={l.status} />
                  {l.status === "pending" && (
                    <Button variant="ghost" size="sm" loading={cancel.isPending && cancel.variables === l.id} disabled={cancel.isPending}
                      onClick={() => cancel.mutate(l.id)}>Cancel</Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
      {open && <RequestLeaveDialog onClose={() => setOpen(false)} />}
    </Card>
  )
}

function RequestLeaveDialog({ onClose }: { onClose: () => void }) {
  const { config } = useAuth()
  const today = config?.studio_today ?? ""
  const [start, setStart] = useState(today)
  const [end, setEnd] = useState(today)
  const [endTouched, setEndTouched] = useState(false)
  const [reason, setReason] = useState("")
  const save = useAction(
    () => api.post<Leave>("/me/leave", { start, end, reason: reason.trim() }),
    { success: "Leave requested", invalidate: LEAVE_KEYS, onSuccess: onClose },
  )
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(undefined) }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Request leave</DialogTitle>
            <DialogDescription>You'll get a notification when it is approved or rejected.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <Field label="From" htmlFor="lv-start">
              <Input id="lv-start" type="date" required value={start}
                onChange={(e) => { setStart(e.target.value); if (!endTouched || e.target.value > end) setEnd(e.target.value) }} />
            </Field>
            <Field label="To" htmlFor="lv-end">
              <Input id="lv-end" type="date" required min={start} value={end} onChange={(e) => { setEnd(e.target.value); setEndTouched(true) }} />
            </Field>
          </div>
          <Field label="Reason" htmlFor="lv-reason">
            <Textarea id="lv-reason" required minLength={3} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Family function out of town" />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending} disabled={reason.trim().length < 3 || !start || end < start}>Send request</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
