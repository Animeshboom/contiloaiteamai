import { useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { LayoutGrid, List, Plus } from "lucide-react"

import { AssignmentCard } from "@/components/assignment-card"
import { AssignmentDetailDialog } from "@/components/assignment-detail"
import { AssignmentFormDialog } from "@/components/assignment-form"
import { AssignmentStatusBadge, EmptyState, ErrorState, LoadingRows, PageHeader, PriorityBadge, assignmentStatusLabel } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { NativeSelect } from "@/components/ui/form-controls"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAuth } from "@/lib/auth-context"
import { formatDateTime, relativeDeadline, titleCase } from "@/lib/format"
import { useAssignments, useProjects, useUsers } from "@/lib/queries"
import type { AssignmentStatus, Priority } from "@/lib/types"
import { cn } from "@/lib/utils"

const STATUSES: AssignmentStatus[] = ["assigned", "in_progress", "submitted", "revision_required", "approved", "completed"]

export default function AssignmentsPage() {
  const { user } = useAuth()
  const isArtist = user?.role === "artist"
  const [params, setParams] = useSearchParams()
  const [view, setView] = useState<"table" | "cards">(isArtist ? "cards" : "table")

  const filters = {
    status: params.get("status") ?? undefined,
    project_id: params.get("project_id") ?? undefined,
    artist_id: params.get("artist_id") ?? undefined,
    priority: params.get("priority") ?? undefined,
    overdue: params.get("overdue") === "1" ? true : undefined,
  }
  const { data, isLoading, error, refetch } = useAssignments(filters)
  const projects = useProjects()
  const artists = useUsers({ role: "artist" }, !isArtist)

  const openId = Number(params.get("open")) || null
  const selected = useMemo(() => data?.find((a) => a.id === openId) ?? null, [data, openId])

  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params)
    if (v) next.set(k, v)
    else next.delete(k)
    setParams(next, { replace: true })
  }
  const anyFilter = Object.values(filters).some(Boolean)

  return (
    <>
      <PageHeader
        title={isArtist ? "My assignments" : "Assignments"}
        description={isArtist ? "Scenes and deliverables assigned to you." : "Distribute scenes and deliverables to artists and track each artist's progress."}
        actions={!isArtist && <Button onClick={() => set("new", "1")}><Plus />New assignment</Button>}
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <NativeSelect className="w-44" value={filters.status ?? ""} onChange={(e) => set("status", e.target.value || null)} aria-label="Status">
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{assignmentStatusLabel(s)}</option>)}
        </NativeSelect>
        <NativeSelect className="w-52" value={filters.project_id ?? ""} onChange={(e) => set("project_id", e.target.value || null)} aria-label="Project">
          <option value="">All projects</option>
          {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.title}</option>)}
        </NativeSelect>
        {!isArtist && (
          <NativeSelect className="w-52" value={filters.artist_id ?? ""} onChange={(e) => set("artist_id", e.target.value || null)} aria-label="Artist">
            <option value="">All artists</option>
            {artists.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </NativeSelect>
        )}
        <NativeSelect className="w-36" value={filters.priority ?? ""} onChange={(e) => set("priority", e.target.value || null)} aria-label="Priority">
          <option value="">Any priority</option>
          {(["urgent", "high", "medium", "low"] as Priority[]).map((p) => <option key={p} value={p}>{titleCase(p)}</option>)}
        </NativeSelect>
        <Button variant={filters.overdue ? "secondary" : "outline"} size="sm" onClick={() => set("overdue", filters.overdue ? null : "1")}>
          Overdue only
        </Button>
        {anyFilter && <Button variant="ghost" size="sm" onClick={() => setParams({}, { replace: true })}>Clear</Button>}
        <div className="ml-auto flex rounded-md border p-0.5">
          <Button variant={view === "table" ? "secondary" : "ghost"} size="icon" className="size-7" onClick={() => setView("table")} aria-label="Table view"><List /></Button>
          <Button variant={view === "cards" ? "secondary" : "ghost"} size="icon" className="size-7" onClick={() => setView("cards")} aria-label="Card view"><LayoutGrid /></Button>
        </div>
      </div>

      {error ? <ErrorState error={error} onRetry={refetch} /> : isLoading ? <LoadingRows /> : !data?.length ? (
        <EmptyState
          title={anyFilter ? "No assignments match these filters" : isArtist ? "No assignments yet" : "No assignments yet"}
          description={isArtist ? "When your team lead assigns scenes to you, they'll appear here." : "Create an assignment to distribute scenes to your artists."}
          action={!isArtist && !anyFilter && <Button size="sm" onClick={() => set("new", "1")}><Plus />New assignment</Button>}
        />
      ) : view === "cards" ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.map((a) => <AssignmentCard key={a.id} assignment={a} viewerId={user?.id} to={`?${new URLSearchParams({ ...Object.fromEntries(params), open: String(a.id) })}`} />)}
        </div>
      ) : (
        <Card className="p-1">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Assignment</TableHead><TableHead>Scenes</TableHead>
                {!isArtist && <TableHead>Artists</TableHead>}
                <TableHead>Priority</TableHead><TableHead>Status</TableHead><TableHead>Deadline</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((a) => {
                const dl = relativeDeadline(a.deadline)
                const done = a.status === "approved" || a.status === "completed"
                const mine = a.assignees.find((x) => x.user_id === user?.id)
                return (
                  <TableRow key={a.id} className="cursor-pointer" onClick={() => set("open", String(a.id))}>
                    <TableCell>
                      <div className="font-mono text-[11px] text-muted-foreground">{a.project_code}{a.episode_number != null && ` · EP${String(a.episode_number).padStart(2, "0")}`}</div>
                      <div className="max-w-xs truncate font-medium">{a.title}</div>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{a.scenes.length || "—"}</TableCell>
                    {!isArtist && <TableCell className="max-w-[12rem] truncate text-xs">{a.assignees.map((x) => x.full_name.replace(/ \(.*\)/, "")).join(", ")}</TableCell>}
                    <TableCell><PriorityBadge priority={a.priority} /></TableCell>
                    <TableCell><AssignmentStatusBadge status={isArtist && mine ? mine.status : a.status} /></TableCell>
                    <TableCell className="whitespace-nowrap text-xs">
                      <div>{formatDateTime(a.deadline)}</div>
                      {!done && <div className={cn("text-muted-foreground", dl.overdue && "text-destructive")}>{dl.text}</div>}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </Card>
      )}

      {selected && (
        <AssignmentDetailDialog assignment={selected} viewerId={user?.id} canManage={!isArtist} onClose={() => set("open", null)} />
      )}
      {!isArtist && params.get("new") === "1" && (
        <AssignmentFormDialog open onOpenChange={(o) => !o && set("new", null)} />
      )}
    </>
  )
}
