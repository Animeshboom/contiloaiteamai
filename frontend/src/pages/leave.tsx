import { useState, type FormEvent } from "react"
import { Check, X } from "lucide-react"

import { EmptyState, ErrorState, LeaveStatusBadge, LoadingRows, PageHeader } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Field, NativeSelect, Textarea } from "@/components/ui/form-controls"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { formatDateRange, formatDateTime } from "@/lib/format"
import { LEAVE_KEYS, useAction, useLeave, useTeams } from "@/lib/queries"
import type { Leave, LeaveStatus } from "@/lib/types"

/** Managers: leave requests to approve or reject. Leads see their team's artists; admins see everyone (incl. leads). */
export default function LeavePage() {
  const { user } = useAuth()
  const isAdmin = user?.role === "admin"
  const [status, setStatus] = useState<LeaveStatus | "">("pending")
  const [teamId, setTeamId] = useState("")
  const [deciding, setDeciding] = useState<{ leave: Leave; decision: "approved" | "rejected" } | null>(null)
  const teams = useTeams()
  const { data, isLoading, error, refetch } = useLeave({ status: status || undefined, team_id: teamId || undefined })

  return (
    <>
      <PageHeader title="Leave" description={isAdmin ? "Leave requests from everyone, including team leads." : "Leave requests from your team. Request your own leave on the Attendance page; an administrator decides it."} />
      <div className="space-y-6">
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <NativeSelect className="w-44" value={status} onChange={(e) => setStatus(e.target.value as LeaveStatus | "")} aria-label="Leave status">
              <option value="pending">Pending</option>
              <option value="">All statuses</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
              <option value="cancelled">Cancelled</option>
            </NativeSelect>
            {isAdmin && (
              <NativeSelect className="w-48" value={teamId} onChange={(e) => setTeamId(e.target.value)} aria-label="Team">
                <option value="">All teams</option>
                {teams.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </NativeSelect>
            )}
          </div>
          {error ? <ErrorState error={error} onRetry={refetch} /> : isLoading ? <LoadingRows /> : !data?.length ? (
            <EmptyState title={status === "pending" ? "No pending leave requests" : "No leave requests"} />
          ) : (
            <Card className="p-1">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Person</TableHead><TableHead>Dates</TableHead><TableHead>Reason</TableHead>
                    <TableHead>Requested</TableHead><TableHead>Status</TableHead><TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.map((l) => (
                    <TableRow key={l.id}>
                      <TableCell>
                        <div className="font-medium">{l.person}</div>
                        <div className="text-xs text-muted-foreground">{l.team_name ?? "No team"}</div>
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-sm">
                        {formatDateRange(l.start, l.end)}
                        <div className="text-xs text-muted-foreground">{l.days} day{l.days === 1 ? "" : "s"}</div>
                      </TableCell>
                      <TableCell className="max-w-[18rem] text-sm"><div className="line-clamp-3" title={l.reason}>{l.reason}</div></TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTime(l.created_at)}</TableCell>
                      <TableCell>
                        <LeaveStatusBadge status={l.status} />
                        {l.decision_note && <div className="mt-0.5 max-w-[14rem] truncate text-[11px] text-muted-foreground" title={l.decision_note}>{l.decision_note}</div>}
                        {l.decided_by && <div className="text-[11px] text-muted-foreground">by {l.decided_by}</div>}
                      </TableCell>
                      <TableCell>
                        {l.status === "pending" && l.user_id !== user?.id && (
                          <div className="flex justify-end gap-1">
                            <Button size="sm" variant="outline" onClick={() => setDeciding({ leave: l, decision: "approved" })} aria-label={`Approve leave for ${l.person}`}><Check />Approve</Button>
                            <Button size="sm" variant="outline" onClick={() => setDeciding({ leave: l, decision: "rejected" })} aria-label={`Reject leave for ${l.person}`}><X />Reject</Button>
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          )}
        </div>
      </div>
      {deciding && <DecideDialog leave={deciding.leave} decision={deciding.decision} onClose={() => setDeciding(null)} />}
    </>
  )
}

function DecideDialog({ leave, decision, onClose }: { leave: Leave; decision: "approved" | "rejected"; onClose: () => void }) {
  const [note, setNote] = useState("")
  const reject = decision === "rejected"
  const save = useAction(
    () => api.post<Leave>(`/leave/${leave.id}/decide`, { decision, ...(note.trim() ? { note: note.trim() } : {}) }),
    { success: reject ? "Leave rejected" : "Leave approved", invalidate: LEAVE_KEYS, onSuccess: onClose },
  )
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(undefined) }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{reject ? "Reject leave" : "Approve leave"}</DialogTitle>
            <DialogDescription>{leave.person} · {formatDateRange(leave.start, leave.end)} · {leave.days} day{leave.days === 1 ? "" : "s"}</DialogDescription>
          </DialogHeader>
          <p className="rounded-md border bg-muted/40 p-3 text-sm">{leave.reason}</p>
          <Field label={reject ? "Note for them" : "Note (optional)"} htmlFor="lv-note" hint={reject ? "Required. They see this." : undefined}>
            <Textarea id="lv-note" required={reject} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)}
              placeholder={reject ? "e.g. Delivery week; please pick other dates" : ""} />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant={reject ? "destructive" : "default"} loading={save.isPending} disabled={reject && !note.trim()}>
              {reject ? "Reject" : "Approve"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
