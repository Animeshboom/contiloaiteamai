import { useSearchParams } from "react-router-dom"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common"
import { SubmissionDialog } from "@/components/submission-dialog"
import { SceneStateChip, SubmissionStatusBadge } from "@/components/submission-view"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { NativeSelect } from "@/components/ui/form-controls"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAuth } from "@/lib/auth-context"
import { formatDate, formatDateTime } from "@/lib/format"
import { useProjects, useSubmissions, useUsers } from "@/lib/queries"
import type { Submission, SubmissionStatus } from "@/lib/types"

type Mode = "lead" | "artist-reviews" | "artist-history"

const COPY: Record<Mode, { title: string; description: string; empty: string }> = {
  lead: { title: "Submissions", description: "Every submission from your team, including all revisions.", empty: "No submissions yet" },
  "artist-reviews": { title: "My reviews", description: "Feedback and decisions from your team lead.", empty: "Nothing has been reviewed yet" },
  "artist-history": { title: "Work history", description: "Everything you've submitted, by day.", empty: "You haven't submitted any work yet" },
}

export default function SubmissionsPage({ mode }: { mode: Mode }) {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const isLead = mode === "lead"
  const filters = {
    status: params.get("status") ?? undefined,
    artist_id: params.get("artist_id") ?? undefined,
    project_id: params.get("project_id") ?? undefined,
    assignment_id: params.get("assignment_id") ?? undefined,
  }
  const { data, isLoading, error, refetch } = useSubmissions(filters)
  const projects = useProjects()
  const artists = useUsers({ role: "artist" }, user?.role !== "artist")
  const rows = mode === "artist-reviews" ? (data ?? []).filter((s) => s.reviews.length > 0) : data ?? []
  const openId = Number(params.get("open")) || null
  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params)
    if (v) next.set(k, v)
    else next.delete(k)
    setParams(next, { replace: true })
  }

  return (
    <>
      <PageHeader title={COPY[mode].title} description={COPY[mode].description} />
      <div className="mb-4 flex flex-wrap gap-2">
        <NativeSelect className="w-48" value={filters.status ?? ""} onChange={(e) => set("status", e.target.value || null)} aria-label="Status">
          <option value="">All statuses</option>
          {mode !== "artist-reviews" && <option value="pending_review">Awaiting review</option>}
          <option value="approved">Approved</option>
          <option value="rejected">Revision required</option>
        </NativeSelect>
        <NativeSelect className="w-56" value={filters.project_id ?? ""} onChange={(e) => set("project_id", e.target.value || null)} aria-label="Project">
          <option value="">All projects</option>
          {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.title}</option>)}
        </NativeSelect>
        {filters.assignment_id && <Button variant="secondary" size="sm" onClick={() => set("assignment_id", null)}>Assignment #{filters.assignment_id} ✕</Button>}
        {isLead && (
          <NativeSelect className="w-56" value={filters.artist_id ?? ""} onChange={(e) => set("artist_id", e.target.value || null)} aria-label="Artist">
            <option value="">All artists</option>
            {artists.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </NativeSelect>
        )}
      </div>

      {error ? <ErrorState error={error} onRetry={refetch} /> : isLoading ? <LoadingRows /> : rows.length === 0 ? (
        <EmptyState title={COPY[mode].empty} />
      ) : mode === "artist-history" ? (
        <HistoryTimeline rows={rows} onOpen={(id) => set("open", String(id))} />
      ) : (
        <Card className="p-1">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>#</TableHead><TableHead>Assignment</TableHead>{isLead && <TableHead>Artist</TableHead>}
                <TableHead>Scenes</TableHead><TableHead>Status</TableHead><TableHead>Submitted</TableHead>
                {mode === "artist-reviews" && <TableHead>Feedback</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((s) => (
                <TableRow key={s.id} className="cursor-pointer" onClick={() => set("open", String(s.id))}>
                  <TableCell className="font-mono text-xs text-muted-foreground">#{s.id}<div>rev {s.revision_number}</div></TableCell>
                  <TableCell>
                    <div className="font-mono text-[11px] text-muted-foreground">{s.project_code}</div>
                    <div className="max-w-xs truncate font-medium">{s.assignment_title}</div>
                  </TableCell>
                  {isLead && <TableCell className="text-sm">{s.artist_name}</TableCell>}
                  <TableCell><div className="flex max-w-[16rem] flex-wrap gap-1">{s.deliverables.map((d) => <SceneStateChip key={d.id} label={d.label.replace(/^EP\d+ /, "")} state={d.status} />)}</div></TableCell>
                  <TableCell>
                    <div className="flex flex-col items-start gap-1">
                      <SubmissionStatusBadge status={s.status} />
                      {s.is_late && <Badge tone="red">Late</Badge>}
                    </div>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-xs">{formatDateTime(s.submitted_at)}</TableCell>
                  {mode === "artist-reviews" && <TableCell className="max-w-xs truncate text-xs text-muted-foreground">{s.reviews.at(-1)?.feedback ?? "—"}</TableCell>}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
      {openId && <SubmissionDialog key={openId} id={openId} onClose={() => set("open", null)} />}
    </>
  )
}

function HistoryTimeline({ rows, onOpen }: { rows: Submission[]; onOpen: (id: number) => void }) {
  const byDay = new Map<string, Submission[]>()
  rows.forEach((s) => byDay.set(s.submission_date, [...(byDay.get(s.submission_date) ?? []), s]))
  return (
    <div className="space-y-6">
      {[...byDay.entries()].map(([day, subs]) => (
        <div key={day}>
          <div className="mb-2 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">{formatDate(day, true)}</div>
          <div className="space-y-2">
            {subs.map((s) => (
              <button key={s.id} type="button" onClick={() => onOpen(s.id)}
                className="flex w-full flex-col gap-2 rounded-lg border bg-card p-4 text-left transition-colors hover:border-primary/40 sm:flex-row sm:items-center cursor-pointer">
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-[11px] text-muted-foreground">#{s.id} · rev {s.revision_number} · {s.project_code}</div>
                  <div className="truncate font-medium">{s.assignment_title}</div>
                  <div className="mt-1.5 flex flex-wrap gap-1">{s.deliverables.map((d) => <SceneStateChip key={d.id} label={d.label} state={d.status} />)}</div>
                </div>
                <div className="flex items-center gap-2"><SubmissionStatusBadge status={s.status as SubmissionStatus} />{s.is_late && <Badge tone="red">Late</Badge>}</div>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
