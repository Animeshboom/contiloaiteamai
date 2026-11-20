import type { ReactNode } from "react"
import { Link } from "react-router-dom"
import { AlarmClock, CalendarDays, Inbox, UserX } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/misc"
import { formatDate, formatDateRange, formatDateTime, relativeDeadline } from "@/lib/format"
import { useLeadToday } from "@/lib/queries"
import type { LeadTaskItem } from "@/lib/types"
import { cn } from "@/lib/utils"

const MAX = 6
const ABSENT_LABEL: Record<string, string> = { absent: "Absent", not_checked_in: "Not checked in" }

function Section({ title, icon, count, tone = "amber", more, children }: {
  title: string; icon: ReactNode; count: number; tone?: "amber" | "red"; more?: ReactNode; children: ReactNode
}) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm [&_svg]:size-4 [&_svg]:text-muted-foreground">{icon}{title}</CardTitle>
        <Badge tone={count ? tone : "neutral"} aria-label={`${title}: ${count}`}>{count}</Badge>
      </CardHeader>
      <CardContent className="pt-0">
        {count === 0 ? <p className="py-2 text-sm text-muted-foreground">All clear</p> : <ul className="divide-y">{children}</ul>}
        {more}
      </CardContent>
    </Card>
  )
}

const Row = ({ to, children }: { to: string; children: ReactNode }) => (
  <li><Link to={to} className="flex items-center justify-between gap-3 py-2 text-sm hover:text-primary">{children}</Link></li>
)

const More = ({ n, to }: { n: number; to: string }) =>
  n > MAX ? <Link to={to} className="mt-1 block text-xs text-muted-foreground hover:text-primary">+{n - MAX} more</Link> : null

function TaskRow({ t, overdue }: { t: LeadTaskItem; overdue?: boolean }) {
  const dl = relativeDeadline(t.deadline)
  return (
    <Row to={`/lead/assignments?open=${t.assignment_id}`}>
      <span className="min-w-0">
        <span className="block truncate font-medium">{t.title}</span>
        <span className="block truncate text-xs text-muted-foreground">{t.person}</span>
      </span>
      <span className={cn("shrink-0 text-right text-xs", overdue ? "text-destructive" : "text-muted-foreground")} title={formatDateTime(t.deadline)}>
        {overdue ? dl.text : formatDateTime(t.deadline)}
      </span>
    </Row>
  )
}

/** Team lead's "what needs me now" panel: reviews, leave, overdue/due work and who is missing today. */
export function LeadTodayPanel() {
  const { data } = useLeadToday()
  if (!data) return <div className="grid gap-4 md:grid-cols-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-40" />)}</div>
  const c = data.counts
  const tasks = [...data.overdue.map((t) => ({ t, overdue: true })), ...data.due_today.map((t) => ({ t, overdue: false }))]

  return (
    <section aria-label="Today" className="space-y-3">
      <h2 className="text-sm font-semibold">Today · {formatDate(data.date, true)}{!data.is_work_day && <span className="ml-2 font-normal text-muted-foreground">(not a working day)</span>}</h2>
      <div className="grid gap-4 md:grid-cols-2">
        <Section title="Reviews waiting" icon={<Inbox />} count={c.reviews} more={<More n={c.reviews} to="/lead/reviews" />}>
          {data.reviews.slice(0, MAX).map((r) => (
            <Row key={r.submission_id} to={`/lead/reviews?open=${r.submission_id}`}>
              <span className="min-w-0">
                <span className="block truncate font-medium">{r.person}</span>
                <span className="block truncate text-xs text-muted-foreground">{r.assignment}</span>
              </span>
              <span className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                {r.late && <Badge tone="red">late</Badge>}{formatDateTime(r.submitted_at)}
              </span>
            </Row>
          ))}
        </Section>

        <Section title="Leave requests" icon={<CalendarDays />} count={c.leave_requests} more={<More n={c.leave_requests} to="/lead/leave" />}>
          {data.leave_requests.slice(0, MAX).map((l) => (
            <Row key={l.id} to="/lead/leave">
              <span className="min-w-0">
                <span className="block truncate font-medium">{l.person}</span>
                <span className="block truncate text-xs text-muted-foreground">{l.reason}</span>
              </span>
              <span className="shrink-0 text-xs text-muted-foreground">{formatDateRange(l.start, l.end)}</span>
            </Row>
          ))}
        </Section>

        <Section title="Overdue & due today" icon={<AlarmClock />} count={c.overdue + c.due_today} tone={c.overdue ? "red" : "amber"}
          more={<More n={c.overdue + c.due_today} to="/lead/assignments" />}>
          {tasks.slice(0, MAX).map(({ t, overdue }) => <TaskRow key={`${t.assignment_id}-${t.person_id}`} t={t} overdue={overdue} />)}
        </Section>

        <Section title="Absent / not checked in" icon={<UserX />} count={c.absent} tone="red" more={<More n={c.absent} to="/lead/attendance" />}>
          {data.absent.slice(0, MAX).map((p) => (
            <Row key={p.person_id} to="/lead/attendance">
              <span className="truncate font-medium">{p.person}</span>
              <Badge tone={p.status === "absent" ? "red" : "neutral"}>{ABSENT_LABEL[p.status] ?? p.status}</Badge>
            </Row>
          ))}
        </Section>
      </div>
    </section>
  )
}
