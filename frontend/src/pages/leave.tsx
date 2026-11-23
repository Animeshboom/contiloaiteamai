import { useState, type FormEvent } from "react"
import { AlertTriangle, CalendarDays, CalendarPlus, Check, Users, X } from "lucide-react"

import { EmptyState, ErrorState, LeaveStatusBadge, LeaveTypeBadge, LoadingRows, PageHeader } from "@/components/common"
import { MyLeaveCard, RequestLeaveDialog } from "@/components/my-leave"
import { Badge } from "@/components/ui/badge"
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

/** Managers: leave requests to approve or reject, upcoming absences timeline, and own requests. */
export default function LeavePage() {
  const { user, config } = useAuth()
  const today = config?.studio_today ?? ""
  const isAdmin = user?.role === "admin"
  const [tab, setTab] = useState<"team" | "my">("team")
  const [status, setStatus] = useState<LeaveStatus | "">("pending")
  const [teamId, setTeamId] = useState("")
  const [openRequest, setOpenRequest] = useState(false)
  const [deciding, setDeciding] = useState<{ leave: Leave; decision: "approved" | "rejected" } | null>(null)

  const teams = useTeams()
  const { data, isLoading, error, refetch } = useLeave({ status: status || undefined, team_id: teamId || undefined })
  const approvedQuery = useLeave({ status: "approved", team_id: teamId || undefined })

  // Calculate upcoming leaves within the next 14 days for the "Who's Away" strip
  const upcomingAbsences = (approvedQuery.data ?? []).filter((l) => {
    if (!today) return true
    return l.end >= today
  }).slice(0, 8)

  return (
    <>
      <PageHeader
        title="Leave"
        description="Review team requests, track upcoming absences, or submit your own leave request."
        actions={
          <Button onClick={() => setOpenRequest(true)}>
            <CalendarPlus className="mr-1.5 h-4 w-4" />
            Request leave
          </Button>
        }
      />

      <div className="space-y-6">
        {/* Navigation Tabs */}
        <div className="flex border-b border-border">
          <button
            type="button"
            className={`border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              tab === "team"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => setTab("team")}
          >
            Team Requests {data?.filter((l) => l.status === "pending").length ? (
              <Badge tone="amber" className="ml-1.5 px-1.5 py-0 text-[10px]">
                {data.filter((l) => l.status === "pending").length}
              </Badge>
            ) : null}
          </button>
          <button
            type="button"
            className={`border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              tab === "my"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => setTab("my")}
          >
            My Leave
          </button>
        </div>

        {tab === "my" ? (
          <MyLeaveCard />
        ) : (
          <div className="space-y-6">
            {/* "Who's Away" Upcoming Absences Timeline Bar */}
            <Card className="p-4 bg-muted/30">
              <div className="flex items-center justify-between pb-2 border-b border-border/50">
                <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <CalendarDays className="h-4 w-4 text-primary" />
                  <span>Who's Away (Upcoming Absences)</span>
                </div>
                <span className="text-xs text-muted-foreground">Next 14 Days</span>
              </div>
              <div className="mt-3">
                {approvedQuery.isLoading ? (
                  <p className="text-xs text-muted-foreground">Loading schedule...</p>
                ) : !upcomingAbsences.length ? (
                  <p className="text-xs text-muted-foreground">
                    No approved leaves scheduled in the next 14 days — full team attendance expected.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2.5">
                    {upcomingAbsences.map((l) => (
                      <div
                        key={l.id}
                        className="flex items-center gap-2 rounded-md border border-border/70 bg-card px-2.5 py-1.5 shadow-xs"
                      >
                        <div className="flex flex-col">
                          <span className="text-xs font-medium text-foreground">{l.person}</span>
                          <span className="text-[11px] text-muted-foreground">
                            {formatDateRange(l.start, l.end)} ({l.days} {l.days === 1 ? "day" : "days"})
                          </span>
                        </div>
                        <LeaveTypeBadge type={l.leave_type} halfDay={l.half_day} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Card>

            {/* Filter Bar */}
            <div className="flex flex-wrap gap-2">
              <NativeSelect
                className="w-44"
                value={status}
                onChange={(e) => setStatus(e.target.value as LeaveStatus | "")}
                aria-label="Leave status"
              >
                <option value="pending">Pending</option>
                <option value="">All statuses</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
                <option value="cancelled">Cancelled</option>
              </NativeSelect>
              {isAdmin && (
                <NativeSelect
                  className="w-48"
                  value={teamId}
                  onChange={(e) => setTeamId(e.target.value)}
                  aria-label="Team"
                >
                  <option value="">All teams</option>
                  {teams.data?.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </NativeSelect>
              )}
            </div>

            {/* Requests Table */}
            {error ? (
              <ErrorState error={error} onRetry={refetch} />
            ) : isLoading ? (
              <LoadingRows />
            ) : !data?.length ? (
              <EmptyState title={status === "pending" ? "No pending leave requests" : "No leave requests"} />
            ) : (
              <Card className="p-1">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Person & Usage</TableHead>
                      <TableHead>Leave Type & Dates</TableHead>
                      <TableHead>Impact & Alerts</TableHead>
                      <TableHead>Reason</TableHead>
                      <TableHead>Requested</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.map((l) => (
                      <TableRow key={l.id}>
                        <TableCell>
                          <div className="font-medium text-foreground">{l.person}</div>
                          <div className="text-xs text-muted-foreground">{l.team_name ?? "No team"}</div>
                          <div className="text-[11px] text-muted-foreground mt-0.5">
                            Year: <span className="font-medium text-foreground">{l.days_taken_year ?? 0}d</span>
                            {l.days_taken_month ? ` (${l.days_taken_month}d this mo)` : ""}
                          </div>
                        </TableCell>

                        <TableCell className="whitespace-nowrap">
                          <div className="flex items-center gap-1.5 mb-1">
                            <LeaveTypeBadge type={l.leave_type} halfDay={l.half_day} />
                          </div>
                          <div className="text-sm font-medium text-foreground">{formatDateRange(l.start, l.end)}</div>
                          <div className="text-xs text-muted-foreground">
                            {l.days} {l.days === 1 ? "day" : "days"}
                          </div>
                        </TableCell>

                        <TableCell>
                          <div className="flex flex-col gap-1 text-[11px]">
                            {l.active_tasks_count ? (
                              <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400 font-medium bg-amber-500/10 px-1.5 py-0.5 rounded w-fit">
                                <AlertTriangle className="h-3 w-3" />
                                {l.active_tasks_count} active task deadline(s)
                              </span>
                            ) : null}
                            {l.team_overlap_count ? (
                              <span className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 font-medium bg-blue-500/10 px-1.5 py-0.5 rounded w-fit">
                                <Users className="h-3 w-3" />
                                {l.team_overlap_count} teammate(s) off
                              </span>
                            ) : null}
                            {!l.active_tasks_count && !l.team_overlap_count && (
                              <span className="text-muted-foreground">No conflicts</span>
                            )}
                          </div>
                        </TableCell>

                        <TableCell className="max-w-[16rem] text-sm">
                          <div className="line-clamp-2" title={l.reason}>{l.reason}</div>
                        </TableCell>

                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {formatDateTime(l.created_at)}
                        </TableCell>

                        <TableCell>
                          <LeaveStatusBadge status={l.status} />
                          {l.decision_note && (
                            <div className="mt-0.5 max-w-[12rem] truncate text-[11px] text-muted-foreground" title={l.decision_note}>
                              {l.decision_note}
                            </div>
                          )}
                          {l.decided_by && <div className="text-[11px] text-muted-foreground">by {l.decided_by}</div>}
                        </TableCell>

                        <TableCell>
                          {l.status === "pending" && l.user_id !== user?.id && (
                            <div className="flex justify-end gap-1">
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => setDeciding({ leave: l, decision: "approved" })}
                                aria-label={`Approve leave for ${l.person}`}
                              >
                                <Check className="h-4 w-4" />
                                Approve
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => setDeciding({ leave: l, decision: "rejected" })}
                                aria-label={`Reject leave for ${l.person}`}
                              >
                                <X className="h-4 w-4" />
                                Reject
                              </Button>
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
        )}
      </div>

      {openRequest && <RequestLeaveDialog onClose={() => setOpenRequest(false)} />}
      {deciding && <DecideDialog leave={deciding.leave} decision={deciding.decision} onClose={() => setDeciding(null)} />}
    </>
  )
}

function DecideDialog({ leave, decision, onClose }: { leave: Leave; decision: "approved" | "rejected"; onClose: () => void }) {
  const [note, setNote] = useState("")
  const reject = decision === "rejected"
  const save = useAction(
    () => api.post<Leave>(`/leave/${leave.id}/decide`, { decision, ...(note.trim() ? { note: note.trim() } : {}) }),
    { success: `Leave ${decision}`, invalidate: LEAVE_KEYS, onSuccess: onClose },
  )
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(undefined) }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{reject ? "Reject leave request" : "Approve leave request"}</DialogTitle>
            <DialogDescription>
              {leave.person} ({leave.team_name ?? "No team"}) requested {leave.days} {leave.days === 1 ? "day" : "days"} from {formatDateRange(leave.start, leave.end)}.
            </DialogDescription>
          </DialogHeader>

          {/* Impact and Usage Alerts within dialog */}
          <div className="rounded-md border border-border/80 bg-muted/30 p-3 space-y-2 text-xs">
            <div className="flex justify-between items-center text-muted-foreground">
              <span>Leave Type:</span>
              <LeaveTypeBadge type={leave.leave_type} halfDay={leave.half_day} />
            </div>
            <div className="flex justify-between items-center text-muted-foreground">
              <span>Days taken this year:</span>
              <span className="font-medium text-foreground">{leave.days_taken_year ?? 0} days</span>
            </div>

            {leave.active_tasks_count ? (
              <div className="flex items-start gap-1.5 text-amber-600 dark:text-amber-400 font-medium pt-1 border-t border-border/50">
                <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                <span>Notice: {leave.person} has {leave.active_tasks_count} active assigned task(s) with deadlines during this leave.</span>
              </div>
            ) : null}

            {leave.team_overlap_count ? (
              <div className="flex items-start gap-1.5 text-blue-600 dark:text-blue-400 font-medium pt-1 border-t border-border/50">
                <Users className="h-4 w-4 shrink-0 mt-0.5" />
                <span>Team coverage: {leave.team_overlap_count} other member(s) of this team already have approved leave on these dates.</span>
              </div>
            ) : null}
          </div>

          <Field label={reject ? "Reason for rejection (required)" : "Note (optional)"} htmlFor="decide-note">
            <Textarea
              id="decide-note"
              required={reject}
              minLength={reject ? 3 : 0}
              maxLength={1000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={reject ? "e.g. Critical episode delivery deadline this Thursday" : "Optional comment or instructions"}
            />
          </Field>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant={reject ? "destructive" : "default"} loading={save.isPending} disabled={reject && note.trim().length < 3}>
              {reject ? "Reject request" : "Confirm approval"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
