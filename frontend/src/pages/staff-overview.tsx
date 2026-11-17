import { Link } from "react-router-dom"
import { AlarmClock, ClipboardList, Film, ListChecks, UserCheck } from "lucide-react"

import { AttendanceTrendChart, BarList } from "@/components/charts"
import { EmptyState, ErrorState, PageHeader, StatCard, assignmentStatusLabel } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/misc"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAuth } from "@/lib/auth-context"
import { formatDate } from "@/lib/format"
import { useStaffOverview } from "@/lib/queries"
import type { AssignmentStatus } from "@/lib/types"

const STATUS_ORDER: AssignmentStatus[] = ["assigned", "in_progress", "submitted", "revision_required", "approved", "completed"]

export default function StaffOverviewPage() {
  const { user } = useAuth()
  const { data, isLoading, error, refetch } = useStaffOverview()
  const base = user?.role === "admin" ? "/admin" : "/lead"

  if (error) return <ErrorState error={error} onRetry={refetch} />

  return (
    <>
      <PageHeader
        title="Production overview"
        description={data ? `${formatDate(data.date, true)} · ${user?.role === "admin" ? "All teams" : user?.team?.name ?? "Your team"}` : " "}
        actions={user?.role === "team_lead" && (
          <Button asChild><Link to="/lead/assignments?new=1"><ClipboardList />New assignment</Link></Button>
        )}
      />

      {isLoading || !data ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Present today" icon={<UserCheck />} tone="green"
              value={<>{data.attendance_today.present + data.attendance_today.half_day}<span className="text-base text-muted-foreground">/{data.headcount}</span></>}
              hint={`${data.attendance_today.not_checked_in} not checked in · ${data.attendance_today.leave} on leave`}
            />
            <StatCard label="Active assignments" icon={<ListChecks />} value={data.active_assignments} hint={`${data.due_today} due today`} />
            <StatCard label="Overdue" icon={<AlarmClock />} tone={data.overdue ? "red" : "default"} value={data.overdue}
              hint={data.overdue ? "Past deadline, not yet approved" : "Nothing overdue"} />
            <StatCard label="Active projects" icon={<Film />} tone="amber" value={data.active_projects}
              hint={`${data.pending_reviews} submission${data.pending_reviews === 1 ? "" : "s"} awaiting review`} />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Attendance · last 7 days</CardTitle>
                <CardDescription>Headcount by status per studio day</CardDescription>
              </CardHeader>
              <CardContent><AttendanceTrendChart data={data.attendance_trend} /></CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Assignments by status</CardTitle>
                <CardDescription>All assignments in scope</CardDescription>
              </CardHeader>
              <CardContent>
                <BarList
                  items={STATUS_ORDER.map((s) => ({ label: assignmentStatusLabel(s), value: data.assignments_by_status[s] }))}
                  emptyText="No assignments yet"
                />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Artist workload</CardTitle>
              <CardDescription>Per-artist assignment state (each artist tracked separately)</CardDescription>
            </CardHeader>
            <CardContent>
              {data.workload.length === 0 ? (
                <EmptyState title="No assigned work yet" description="Workload appears once artists have assignments."
                  action={user?.role === "team_lead" && <Button asChild size="sm"><Link to="/lead/assignments?new=1">Create assignment</Link></Button>} />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Artist</TableHead>
                      <TableHead className="text-right">Open</TableHead>
                      <TableHead className="text-right">In review</TableHead>
                      <TableHead className="text-right">Approved</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.workload.map((w) => (
                      <TableRow key={w.user_id}>
                        <TableCell className="font-medium">
                          {base === "/lead"
                            ? <Link className="hover:text-primary" to={`/lead/assignments?artist_id=${w.user_id}`}>{w.full_name}</Link>
                            : w.full_name}
                        </TableCell>
                        <TableCell className="text-right font-mono tabular">{w.active}</TableCell>
                        <TableCell className="text-right font-mono tabular">{w.submitted}</TableCell>
                        <TableCell className="text-right font-mono tabular">{w.approved}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </>
  )
}
