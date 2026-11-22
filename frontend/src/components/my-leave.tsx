import { useState, type FormEvent } from "react"
import { CalendarPlus } from "lucide-react"

import { ErrorState, LeaveStatusBadge, LeaveTypeBadge } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Field, Input, NativeSelect, Textarea } from "@/components/ui/form-controls"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { formatDateRange } from "@/lib/format"
import { LEAVE_KEYS, useAction, useMyLeave } from "@/lib/queries"
import type { HalfDayType, Leave, LeaveType } from "@/lib/types"
import { cn } from "@/lib/utils"

/** Request leave + my requests (artists and leads). Leads' requests are decided by an admin. */
export function MyLeaveCard() {
  const { user, config } = useAuth()
  const today = config?.studio_today ?? ""
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
            {data.map((l) => {
              const canCancel = l.status === "pending" || (l.status === "approved" && l.end >= today)
              return (
                <li key={l.id} className="flex flex-wrap items-start justify-between gap-2 py-2.5">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
                      <span>{formatDateRange(l.start, l.end)}</span>
                      <span className="font-normal text-muted-foreground">· {l.days} {l.days === 1 ? "day" : "days"}</span>
                      <LeaveTypeBadge type={l.leave_type} halfDay={l.half_day} />
                    </div>
                    <div className="text-xs text-muted-foreground">{l.reason}</div>
                    {l.decision_note && (
                      <div className={cn("text-xs", l.status === "rejected" ? "text-destructive" : "text-muted-foreground")}>
                        {l.decided_by ? `${l.decided_by}: ` : ""}{l.decision_note}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <LeaveStatusBadge status={l.status} />
                    {canCancel && (
                      <Button variant="ghost" size="sm" loading={cancel.isPending && cancel.variables === l.id} disabled={cancel.isPending}
                        onClick={() => cancel.mutate(l.id)}>Cancel</Button>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
      {open && <RequestLeaveDialog onClose={() => setOpen(false)} />}
    </Card>
  )
}

export function RequestLeaveDialog({ onClose }: { onClose: () => void }) {
  const { config } = useAuth()
  const today = config?.studio_today ?? ""
  const [start, setStart] = useState(today)
  const [end, setEnd] = useState(today)
  const [endTouched, setEndTouched] = useState(false)
  const [leaveType, setLeaveType] = useState<LeaveType>("casual")
  const [isHalfDay, setIsHalfDay] = useState(false)
  const [halfDaySlot, setHalfDaySlot] = useState<HalfDayType>("first_half")
  const [reason, setReason] = useState("")

  const save = useAction(
    () => api.post<Leave>("/me/leave", {
      start,
      end: isHalfDay ? start : end,
      reason: reason.trim(),
      leave_type: leaveType,
      half_day: isHalfDay ? halfDaySlot : undefined,
    }),
    { success: "Leave requested", invalidate: LEAVE_KEYS, onSuccess: onClose },
  )
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(undefined) }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Request leave</DialogTitle>
            <DialogDescription>Select your leave category and date. Approvers will be notified immediately.</DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Leave Type" htmlFor="lv-type">
              <NativeSelect id="lv-type" value={leaveType} onChange={(e) => setLeaveType(e.target.value as LeaveType)}>
                <option value="casual">Casual Leave (CL)</option>
                <option value="sick">Sick / Medical Leave (SL)</option>
                <option value="privilege">Privilege / Vacation (PL)</option>
                <option value="unpaid">Unpaid Leave (LOP)</option>
              </NativeSelect>
            </Field>

            <Field label="Duration" htmlFor="lv-duration">
              <NativeSelect
                id="lv-duration"
                value={isHalfDay ? halfDaySlot : "full"}
                onChange={(e) => {
                  if (e.target.value === "full") {
                    setIsHalfDay(false)
                  } else {
                    setIsHalfDay(true)
                    setHalfDaySlot(e.target.value as HalfDayType)
                    setEnd(start)
                  }
                }}
              >
                <option value="full">Full Day(s)</option>
                <option value="first_half">Half Day (First Half / Morning)</option>
                <option value="second_half">Half Day (Second Half / Afternoon)</option>
              </NativeSelect>
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label={isHalfDay ? "Date" : "From"} htmlFor="lv-start">
              <Input id="lv-start" type="date" required value={start}
                onChange={(e) => {
                  setStart(e.target.value)
                  if (isHalfDay || !endTouched || e.target.value > end) setEnd(e.target.value)
                }} />
            </Field>
            {!isHalfDay && (
              <Field label="To" htmlFor="lv-end">
                <Input id="lv-end" type="date" required min={start} value={end} onChange={(e) => { setEnd(e.target.value); setEndTouched(true) }} />
              </Field>
            )}
          </div>

          <Field label="Reason" htmlFor="lv-reason">
            <Textarea id="lv-reason" required minLength={3} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Doctor appointment, family function, or personal travel" />
          </Field>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending} disabled={reason.trim().length < 3 || !start || (!isHalfDay && end < start)}>Send request</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
