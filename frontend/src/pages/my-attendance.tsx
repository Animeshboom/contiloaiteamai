import { useState } from "react"

import { CheckInCard } from "@/components/check-in-card"
import { AttendanceBadge, EmptyState, ErrorState, LoadingRows, PageHeader, StatCard } from "@/components/common"
import { Card } from "@/components/ui/card"
import { NativeSelect } from "@/components/ui/form-controls"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAuth } from "@/lib/auth-context"
import { addDays, formatDate, formatMinutes, formatTime } from "@/lib/format"
import { useMyAttendance } from "@/lib/queries"

export default function MyAttendancePage() {
  const { config } = useAuth()
  const [days, setDays] = useState(30)
  const end = config?.studio_today
  const start = end ? addDays(end, -days + 1) : undefined
  const { data, isLoading, error, refetch } = useMyAttendance({ start, end })

  const present = data?.filter((r) => r.status === "present").length ?? 0
  const half = data?.filter((r) => r.status === "half_day").length ?? 0
  const leave = data?.filter((r) => r.status === "leave").length ?? 0
  const worked = data?.reduce((s, r) => s + (r.worked_minutes ?? 0), 0) ?? 0

  return (
    <>
      <PageHeader title="My attendance" description="Check in when you start, check out when you finish. Times are in studio time." />
      <div className="space-y-6">
        <CheckInCard />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label={`Present (${days}d)`} value={present} tone="green" />
          <StatCard label="Half days" value={half} />
          <StatCard label="Leave" value={leave} tone="blue" />
          <StatCard label="Hours logged" value={formatMinutes(worked)} />
        </div>
        <Card>
          <div className="flex items-center justify-between border-b px-5 py-3">
            <div className="text-sm font-semibold">History</div>
            <NativeSelect className="w-36" value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Range">
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </NativeSelect>
          </div>
          <div className="p-2">
            {error ? <ErrorState error={error} onRetry={refetch} /> : isLoading ? <LoadingRows /> : !data?.length ? (
              <EmptyState title="No attendance records in this range" description="Check in above to start your record." />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead><TableHead>Status</TableHead><TableHead>Check in</TableHead>
                    <TableHead>Check out</TableHead><TableHead>Worked</TableHead><TableHead>Note</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell className="whitespace-nowrap">{formatDate(r.work_date, true)}</TableCell>
                      <TableCell><AttendanceBadge status={r.status} /></TableCell>
                      <TableCell className="font-mono tabular">{formatTime(r.check_in_at)}</TableCell>
                      <TableCell className="font-mono tabular">{formatTime(r.check_out_at)}</TableCell>
                      <TableCell className="font-mono tabular">{formatMinutes(r.worked_minutes)}</TableCell>
                      <TableCell className="max-w-xs truncate text-xs text-muted-foreground">
                        {r.corrected_at ? `Corrected by lead: ${r.notes ?? ""}` : r.notes ?? ""}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        </Card>
      </div>
    </>
  )
}
