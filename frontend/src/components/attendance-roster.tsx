import { AlertTriangle, CheckCircle2 } from "lucide-react"

import { AttendanceBadge } from "@/components/common"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useShowCheckinTimes } from "@/lib/queries"
import type { ReportMetrics } from "@/lib/types"
import { cn } from "@/lib/utils"

const ORDER: Record<string, number> = { absent: 0, not_checked_in: 1, leave: 2, half_day: 3, present: 4, day_off: 5 }
const MISSING = new Set(["absent", "not_checked_in"])

/** Everyone in the report's scope (staff and students), absent / not checked in first in red, with a count line. */
export function AttendanceRoster({ m }: { m: ReportMetrics }) {
  const showTimes = useShowCheckinTimes()
  const t = m.totals
  const people = [...m.artists].sort((a, b) => (ORDER[a.attendance] ?? 9) - (ORDER[b.attendance] ?? 9) || a.name.localeCompare(b.name))
  const missing = people.filter((a) => MISSING.has(a.attendance))

  return (
    <Card>
      <CardHeader>
        <CardTitle>Today's attendance</CardTitle>
        <CardDescription>
          Present {t.present} of {t.team_members}
          {t.half_day ? ` (half day: ${t.half_day})` : ""} · On leave {t.on_leave} · Absent {t.absent}
          {t.not_checked_in ? ` · Not checked in ${t.not_checked_in}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {missing.length > 0 ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2">
            <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-destructive">
              <AlertTriangle className="size-3.5" />Not present ({missing.length})
            </div>
            <div className="flex flex-wrap gap-1.5">
              {missing.map((a) => (
                <span key={a.name} className="rounded border border-destructive/30 bg-background/60 px-2 py-0.5 text-xs text-destructive">
                  {a.name} · {a.attendance === "absent" ? "absent" : "not checked in"}
                </span>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 text-xs text-success"><CheckCircle2 className="size-3.5" />Everyone is accounted for.</div>
        )}
        <ul className="divide-y rounded-md border text-sm">
          {people.map((a) => (
            <li key={a.name} className={cn("flex items-center justify-between gap-2 px-3 py-1.5", MISSING.has(a.attendance) && "bg-destructive/5")}>
              <span className={cn("truncate", MISSING.has(a.attendance) && "font-medium text-destructive")}>
                {a.name}
                {a.job_title && <span className="ml-1.5 text-xs text-muted-foreground">{a.job_title}</span>}
              </span>
              <span className="flex shrink-0 items-center gap-2">
                {showTimes && a.check_in && <span className="font-mono text-[11px] text-muted-foreground">in {a.check_in}</span>}
                <AttendanceBadge status={a.attendance} />
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
