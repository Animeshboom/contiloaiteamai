import { Link } from "react-router-dom"
import { AlertTriangle, CheckCircle2, CircleDashed } from "lucide-react"

import { EmptyState, LoadingRows } from "@/components/common"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { formatDate, formatTime } from "@/lib/format"
import { useTeamReportStatus } from "@/lib/queries"

/** Admin: which leads have sent their day report in the app, with their issues. */
export function TeamReportStatusCard({ day }: { day: string }) {
  const { data, isLoading } = useTeamReportStatus({ report_date: day || undefined }, !!day)
  const sent = data?.filter((r) => r.submitted_at).length ?? 0

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>Team reports · {day ? formatDate(day, true) : "today"}</CardTitle>
        <CardDescription>{data ? `${sent} of ${data.length} leads have sent their report.` : "Day reports leads send in the app."}</CardDescription>
      </CardHeader>
      <CardContent className="px-3">
        {isLoading ? <LoadingRows rows={3} /> : !data?.length ? <EmptyState title="No team leads" /> : (
          <ul className="divide-y">
            {data.map((r) => {
              const inner = (
                <>
                  <div className="min-w-0">
                    <div className="font-medium">{r.lead}</div>
                    <div className="truncate text-xs text-muted-foreground">{r.teams.join(", ") || "No team"}</div>
                    {r.issues && (
                      <div className="mt-1 flex gap-1.5 text-xs text-warning"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" /><span className="line-clamp-2">{r.issues}</span></div>
                    )}
                  </div>
                  {r.submitted_at ? (
                    <span className="flex shrink-0 items-center gap-1 text-xs text-success"><CheckCircle2 className="size-4" />Sent {formatTime(r.submitted_at)}</span>
                  ) : (
                    <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground"><CircleDashed className="size-4" />Not sent</span>
                  )}
                </>
              )
              return (
                <li key={r.lead_id}>
                  {r.report_id ? (
                    <Link to={`/admin/reports/${r.report_id}`} className="flex items-start justify-between gap-3 rounded-md px-2 py-2.5 hover:bg-accent">{inner}</Link>
                  ) : <div className="flex items-start justify-between gap-3 px-2 py-2.5">{inner}</div>}
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
