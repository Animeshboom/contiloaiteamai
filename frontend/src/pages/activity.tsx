import { Fragment, useState } from "react"
import { ChevronDown, ChevronRight } from "lucide-react"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Checkbox, Input, NativeSelect } from "@/components/ui/form-controls"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { formatDateTime } from "@/lib/format"
import { useActivity, useUsers } from "@/lib/queries"
import type { ActivityEntry } from "@/lib/types"

const TYPES: [string, string][] = [
  ["", "All types"], ["attendance", "Attendance"], ["leave", "Leave"],
  ["user", "Accounts"], ["holiday", "Holidays"], ["announcement", "Announcements"],
  ["assignment", "Assignments"], ["submission", "Submissions"], ["report", "Reports"],
]

function ago(iso: string, now = Date.now()): string {
  const min = Math.round((now - new Date(iso).getTime()) / 60000)
  if (min < 1) return "just now"
  if (min < 60) return `${min}m ago`
  const h = Math.floor(min / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return d < 30 ? `${d}d ago` : formatDateTime(iso)
}

export default function ActivityPage() {
  const [actor, setActor] = useState("")
  const [subject, setSubject] = useState("")
  const [action, setAction] = useState("")
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")
  const [noisy, setNoisy] = useState(false)
  const [open, setOpen] = useState<number | null>(null)
  const users = useUsers({ include_inactive: true })
  const q = useActivity({
    actor_id: actor || undefined, subject_id: subject || undefined, action: action || undefined,
    start: start || undefined, end: end || undefined, include_noisy: noisy || undefined,
  })
  const rows = q.data?.pages.flat() ?? []
  const anyFilter = !!(actor || subject || action || start || end)

  const people = (
    <>{users.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name}{u.employee_code ? ` · ${u.employee_code}` : ""}</option>)}</>
  )

  return (
    <>
      <PageHeader title="Activity" description="Who did what, and when. Routine events (sign-ins, check-ins, progress updates) are hidden unless you ask for them." />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <NativeSelect className="w-48" value={actor} onChange={(e) => setActor(e.target.value)} aria-label="Who">
          <option value="">Anyone</option>{people}
        </NativeSelect>
        <NativeSelect className="w-48" value={subject} onChange={(e) => setSubject(e.target.value)} aria-label="About">
          <option value="">About anyone</option>{people}
        </NativeSelect>
        <NativeSelect className="w-44" value={action} onChange={(e) => setAction(e.target.value)} aria-label="Type">
          {TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </NativeSelect>
        <Input type="date" className="w-38" value={start} max={end || undefined} onChange={(e) => setStart(e.target.value)} aria-label="From" />
        <span className="text-xs text-muted-foreground">to</span>
        <Input type="date" className="w-38" value={end} min={start || undefined} onChange={(e) => setEnd(e.target.value)} aria-label="To" />
        <label className="flex items-center gap-2 text-sm text-muted-foreground"><Checkbox checked={noisy} onCheckedChange={(c) => setNoisy(!!c)} />Show routine events</label>
        {anyFilter && (
          <Button variant="ghost" size="sm" onClick={() => { setActor(""); setSubject(""); setAction(""); setStart(""); setEnd("") }}>Clear</Button>
        )}
      </div>

      {q.error ? <ErrorState error={q.error} onRetry={q.refetch} /> : q.isLoading ? <LoadingRows /> : !rows.length ? (
        <EmptyState title="No activity" description={anyFilter ? "Nothing matches these filters." : undefined} />
      ) : (
        <>
          <Card className="p-1">
            <Table>
              <TableHeader>
                <TableRow><TableHead className="w-8" /><TableHead>When</TableHead><TableHead>Who</TableHead><TableHead>What</TableHead></TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => <Row key={r.id} r={r} open={open === r.id} onToggle={() => setOpen(open === r.id ? null : r.id)} />)}
              </TableBody>
            </Table>
          </Card>
          {q.hasNextPage && (
            <div className="mt-4 flex justify-center">
              <Button variant="outline" loading={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>Load more</Button>
            </div>
          )}
        </>
      )}
    </>
  )
}

function Row({ r, open, onToggle }: { r: ActivityEntry; open: boolean; onToggle: () => void }) {
  return (
    <Fragment>
      <TableRow className="cursor-pointer" onClick={onToggle} aria-expanded={open}>
        <TableCell className="text-muted-foreground [&_svg]:size-4">{open ? <ChevronDown /> : <ChevronRight />}</TableCell>
        <TableCell className="whitespace-nowrap text-xs" title={formatDateTime(r.at)}>{ago(r.at)}</TableCell>
        <TableCell className="whitespace-nowrap text-sm font-medium">{r.actor}</TableCell>
        <TableCell className="text-sm">{r.summary}</TableCell>
      </TableRow>
      {open && (
        <TableRow className="hover:bg-transparent">
          <TableCell />
          <TableCell colSpan={3} className="space-y-2 pb-4">
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
              <span>{formatDateTime(r.at)}</span>
              <span>Action: <span className="font-mono">{r.action}</span></span>
              {r.subject && <span>About: {r.subject}</span>}
              <span>IP: <span className="font-mono">{r.ip ?? "—"}</span></span>
            </div>
            {r.details ? (
              <pre className="max-h-72 overflow-auto rounded-md border bg-muted/40 p-3 font-mono text-xs">{JSON.stringify(r.details, null, 2)}</pre>
            ) : <p className="text-xs text-muted-foreground">No details recorded.</p>}
          </TableCell>
        </TableRow>
      )}
    </Fragment>
  )
}
