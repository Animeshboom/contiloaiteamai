import { AlarmClock, CheckCircle2, ClipboardList, Hourglass, Send, UserCheck, XCircle } from "lucide-react"

import { AttendanceRoster } from "@/components/attendance-roster"
import { AttendanceBadge, StatCard } from "@/components/common"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { formatMinutes, titleCase } from "@/lib/format"
import { useShowCheckinTimes } from "@/lib/queries"
import type { ReportMetrics } from "@/lib/types"

/** Renders a deterministic metrics snapshot. Every figure here comes straight from the API. */
export function ReportMetricsView({ m, compact }: { m: ReportMetrics; compact?: boolean }) {
  const t = m.totals
  const showTimes = useShowCheckinTimes()
  return (
    <div className="space-y-4">
      <div className={compact ? "grid gap-3 sm:grid-cols-2" : "grid gap-3 sm:grid-cols-3 xl:grid-cols-6"}>
        <StatCard label="Present" icon={<UserCheck />} tone="green"
          value={<>{t.present}<span className="text-base text-muted-foreground">/{t.team_members}</span></>}
          hint={`${t.on_leave} leave · ${t.absent} absent${t.not_checked_in ? ` · ${t.not_checked_in} not in` : ""}`} />
        <StatCard label="Assigned" icon={<ClipboardList />} value={t.scenes_assigned} hint={`${t.assignments_distributed} new assignment(s)`} />
        <StatCard label="Submitted" icon={<Send />} tone="amber" value={t.scenes_submitted} hint={`${t.submissions} submission(s)`} />
        <StatCard label="Approved" icon={<CheckCircle2 />} tone="green" value={t.scenes_approved}
          hint={t.approval_rate_pct != null ? `${t.approval_rate_pct}% of reviewed scenes` : "No reviews"} />
        <StatCard label="Rejected" icon={<XCircle />} tone={t.scenes_rejected ? "red" : "default"} value={t.scenes_rejected} hint="Sent back for revision" />
        <StatCard label="Pending review" icon={<Hourglass />} tone={t.pending_reviews ? "amber" : "default"} value={t.pending_reviews}
          hint={`${t.delayed_assignments} delayed · ${t.incomplete_assignments} incomplete`} />
      </div>

      <AttendanceRoster m={m} />

      <Card>
        <CardHeader>
          <CardTitle>Artist performance</CardTitle>
          <CardDescription>Scenes are counted per artist; “approved” only counts lead approvals.</CardDescription>
        </CardHeader>
        <CardContent className="px-2">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead><TableHead>Attendance</TableHead>
                <TableHead className="text-right">Active</TableHead><TableHead className="text-right">Submitted</TableHead>
                <TableHead className="text-right">Approved</TableHead><TableHead className="text-right">Rejected</TableHead>
                <TableHead className="text-right">Pending</TableHead><TableHead className="text-right">Delayed</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {m.artists.map((a) => (
                <TableRow key={a.name}>
                  <TableCell><div className="font-medium">{a.name}</div><div className="text-xs text-muted-foreground">{a.job_title ?? ""}</div></TableCell>
                  <TableCell>
                    <AttendanceBadge status={a.attendance} />
                    {showTimes && a.check_in && <div className="mt-1 font-mono text-[11px] text-muted-foreground">{a.check_in}–{a.check_out ?? "…"} {a.worked_minutes != null && `· ${formatMinutes(a.worked_minutes)}`}</div>}
                    {!showTimes && a.worked_minutes != null && <div className="mt-1 font-mono text-[11px] text-muted-foreground">{formatMinutes(a.worked_minutes)}</div>}
                  </TableCell>
                  {[a.active_assignments, a.scenes_submitted, a.scenes_approved, a.scenes_rejected, a.pending_reviews, a.delayed_assignments].map((v, i) => (
                    <TableCell key={i} className={`text-right font-mono tabular ${i === 5 && v ? "text-destructive" : ""}`}>{v}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {!compact && (m.delayed_assignments.length > 0 || m.remarks.length > 0 || m.projects.length > 0) && (
        <div className="grid gap-4 lg:grid-cols-2">
          {m.projects.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Projects worked on</CardTitle></CardHeader>
              <CardContent className="px-2">
                <Table>
                  <TableHeader><TableRow><TableHead>Project</TableHead><TableHead className="text-right">Active</TableHead><TableHead className="text-right">Subm.</TableHead><TableHead className="text-right">Appr.</TableHead><TableHead className="text-right">Rej.</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {m.projects.map((p) => (
                      <TableRow key={p.code}>
                        <TableCell><span className="font-mono text-xs text-primary">{p.code}</span> {p.title}</TableCell>
                        <TableCell className="text-right font-mono tabular">{p.assignments_active}</TableCell>
                        <TableCell className="text-right font-mono tabular">{p.scenes_submitted}</TableCell>
                        <TableCell className="text-right font-mono tabular">{p.scenes_approved}</TableCell>
                        <TableCell className="text-right font-mono tabular">{p.scenes_rejected}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
          {(m.delayed_assignments.length > 0 || m.remarks.length > 0) && (
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><AlarmClock className="size-4 text-warning" />Remarks</CardTitle><CardDescription>Generated from the records, not by AI</CardDescription></CardHeader>
              <CardContent>
                <ul className="space-y-1.5 text-sm">{m.remarks.map((r) => <li key={r} className="flex gap-2"><span className="text-muted-foreground">•</span>{r}</li>)}</ul>
                {m.delayed_assignments.length > 0 && (
                  <div className="mt-3 border-t pt-3 text-xs text-muted-foreground">
                    Delayed: {m.delayed_assignments.map((d) => `${d.project} ${d.title} (${d.artist.replace(/ \(.*\)/, "")}, ${titleCase(d.status)})`).join(" · ")}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
