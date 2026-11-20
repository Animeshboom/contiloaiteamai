import { useState } from "react"
import { Link } from "react-router-dom"

import { AttendanceBadge, EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAuth } from "@/lib/auth-context"
import { addDays, formatDate, formatMinutes, formatTime } from "@/lib/format"
import { useRoster, useShowCheckinTimes, useStaffOverview, useUserAttendance, useUsers } from "@/lib/queries"
import type { User } from "@/lib/types"

export default function ArtistsPage() {
  const artists = useUsers({ role: "artist" })
  const roster = useRoster()
  const overview = useStaffOverview()
  const [selected, setSelected] = useState<User | null>(null)

  const todayStatus = new Map(roster.data?.map((r) => [r.user_id, r.status]))
  const workload = new Map(overview.data?.workload.map((w) => [w.user_id, w]))

  return (
    <>
      <PageHeader title="Artists" description="Your team's artists, today's attendance and current workload." />
      {artists.error ? <ErrorState error={artists.error} onRetry={artists.refetch} /> : artists.isLoading ? <LoadingRows /> : !artists.data?.length ? (
        <EmptyState title="No artists in your team" description="Ask an admin to add artists to your team." />
      ) : (
        <Card className="p-1">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Artist</TableHead><TableHead>Today</TableHead>
                <TableHead className="text-right">Open</TableHead><TableHead className="text-right">In review</TableHead>
                <TableHead className="text-right">Approved</TableHead><TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {artists.data.map((u) => {
                const w = workload.get(u.id)
                const st = todayStatus.get(u.id)
                return (
                  <TableRow key={u.id}>
                    <TableCell>
                      <div className="font-medium">{u.full_name}</div>
                      <div className="text-xs text-muted-foreground">{u.job_title ?? "—"} · {u.email}</div>
                    </TableCell>
                    <TableCell>{st ? <AttendanceBadge status={st} /> : "—"}</TableCell>
                    <TableCell className="text-right font-mono tabular">{w?.active ?? 0}</TableCell>
                    <TableCell className="text-right font-mono tabular">{w?.submitted ?? 0}</TableCell>
                    <TableCell className="text-right font-mono tabular">{w?.approved ?? 0}</TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      <Button variant="ghost" size="sm" onClick={() => setSelected(u)}>Attendance</Button>
                      <Button variant="ghost" size="sm" asChild><Link to={`/lead/assignments?artist_id=${u.id}`}>Assignments</Link></Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </Card>
      )}
      {selected && <ArtistAttendanceDialog user={selected} onClose={() => setSelected(null)} />}
    </>
  )
}

function ArtistAttendanceDialog({ user, onClose }: { user: User; onClose: () => void }) {
  const { config } = useAuth()
  const showTimes = useShowCheckinTimes()
  const end = config?.studio_today
  const { data, isLoading } = useUserAttendance(user.id, { start: end ? addDays(end, -29) : undefined, end })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent wide>
        <DialogHeader>
          <DialogTitle>{user.full_name}</DialogTitle>
          <DialogDescription>Attendance · last 30 days. Days without a record are absences.</DialogDescription>
        </DialogHeader>
        {isLoading ? <LoadingRows /> : !data?.length ? <EmptyState title="No attendance records in the last 30 days" /> : (
          <Table>
            <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Status</TableHead>{showTimes && <><TableHead>In</TableHead><TableHead>Out</TableHead></>}<TableHead>Worked</TableHead><TableHead>Note</TableHead></TableRow></TableHeader>
            <TableBody>
              {data.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="whitespace-nowrap">{formatDate(r.work_date, true)}</TableCell>
                  <TableCell><AttendanceBadge status={r.status} /></TableCell>
                  {showTimes && <>
                    <TableCell className="font-mono tabular">{formatTime(r.check_in_at)}</TableCell>
                    <TableCell className="font-mono tabular">{formatTime(r.check_out_at)}</TableCell>
                  </>}
                  <TableCell className="font-mono tabular">{formatMinutes(r.worked_minutes)}</TableCell>
                  <TableCell className="max-w-[14rem] truncate text-xs text-muted-foreground">{r.notes ?? ""}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DialogContent>
    </Dialog>
  )
}
