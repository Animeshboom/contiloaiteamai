import { useState } from "react"
import { Link } from "react-router-dom"
import { CheckCheck, Gauge, Pencil, Send, Trash2 } from "lucide-react"

import { AssignmentFormDialog } from "@/components/assignment-form"
import { AssignmentStatusBadge, PriorityBadge, SceneChip } from "@/components/common"
import { Button } from "@/components/ui/button"
import { ConfirmDialog, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { SceneStateChip, SceneStateLegend } from "@/components/submission-view"
import { Field, Textarea } from "@/components/ui/form-controls"
import { api } from "@/lib/api"
import { formatDate, formatDateTime, relativeDeadline } from "@/lib/format"
import { WORK_KEYS, useAction } from "@/lib/queries"
import type { Assignment } from "@/lib/types"
import { cn } from "@/lib/utils"

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 text-sm">{children}</div>
    </div>
  )
}

export function AssignmentDetailDialog({ assignment: a, onClose, canManage, viewerId }: {
  assignment: Assignment; onClose: () => void; canManage: boolean; viewerId?: number
}) {
  const [editing, setEditing] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const del = useAction(() => api.del(`/assignments/${a.id}`), {
    success: "Assignment removed", invalidate: [["assignments"], ["dashboard"]], onSuccess: onClose,
  })
  const dl = relativeDeadline(a.deadline)
  const mine = a.assignees.find((x) => x.user_id === viewerId)
  const myStatus = canManage ? a.status : mine?.status ?? a.status
  const done = myStatus === "approved" || myStatus === "completed"
  const assignees = canManage ? a.assignees : a.assignees.filter((x) => x.user_id === viewerId)
  const [progressOpen, setProgressOpen] = useState(false)
  const complete = useAction(() => api.post(`/assignments/${a.id}/complete`), {
    success: "Assignment marked completed", invalidate: WORK_KEYS,
  })

  return (
    <>
      <Dialog open={!editing} onOpenChange={(o) => !o && onClose()}>
        {/* Do not auto-focus the first button (Delete) when opening. */}
        <DialogContent wide onOpenAutoFocus={(e) => e.preventDefault()}>
          <DialogHeader>
            <div className="font-mono text-[11px] text-muted-foreground">
              #{a.id} · {a.project_code}{a.episode_number != null && ` · EP${String(a.episode_number).padStart(2, "0")} ${a.episode_title}`}
            </div>
            <DialogTitle className="pr-8">{a.title}</DialogTitle>
            <DialogDescription className="flex flex-wrap items-center gap-2 pt-1">
              <AssignmentStatusBadge status={a.status} />
              <PriorityBadge priority={a.priority} />
              {!done && dl.overdue && <span className="text-xs text-destructive">{dl.text}</span>}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 rounded-md border bg-background/40 p-4 sm:grid-cols-4">
            <Meta label="Project">{a.project_title}</Meta>
            <Meta label="Assigned">{formatDate(a.assignment_date)}</Meta>
            <Meta label="Deadline"><span className={cn(!done && dl.overdue && "text-destructive")}>{formatDateTime(a.deadline)}</span></Meta>
            <Meta label="Assigned by">{a.created_by_name}</Meta>
          </div>

          {a.scenes.length > 0 && (
            <Meta label={`Scenes (${a.scenes.length})`}>
              <div className="flex flex-wrap gap-1">{a.scenes.map((s) => <SceneChip key={s.id} label={`EP${String(s.episode_number).padStart(2, "0")} ${s.label}`} />)}</div>
            </Meta>
          )}
          {a.description && <Meta label="Task"><p className="whitespace-pre-wrap text-muted-foreground">{a.description}</p></Meta>}
          {a.expected_deliverables && <Meta label="Expected deliverables"><p className="whitespace-pre-wrap text-muted-foreground">{a.expected_deliverables}</p></Meta>}

          <div>
            <div className="mb-2 flex items-center justify-between">
              <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{canManage ? "Artists" : "Your progress"}</div>
              {a.scenes.length > 0 && <SceneStateLegend />}
            </div>
            <div className="space-y-2">
              {assignees.map((x) => (
                <div key={x.id} className="rounded-md border p-3">
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                    <span className="font-medium">{x.full_name}</span>
                    <AssignmentStatusBadge status={x.status} />
                    <span className="text-xs text-muted-foreground" title="Artist's own estimate — not an approval">Reported {x.reported_progress_pct}%</span>
                    {a.scenes.length > 0 && (
                      <span className="ml-auto font-mono text-xs">
                        <span className="text-success">{x.scenes_approved}</span>/{a.scenes.length} approved · {x.scenes_submitted} submitted
                      </span>
                    )}
                  </div>
                  {x.progress_note && <p className="mt-1 text-xs text-muted-foreground">“{x.progress_note}”</p>}
                  {a.scenes.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {a.scenes.map((s) => <SceneStateChip key={s.id} label={s.label} state={x.scene_states[String(s.id)]} />)}
                    </div>
                  )}
                </div>
              ))}
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">Only scenes approved by a lead count as complete. Reported progress is the artist's own estimate.</p>
          </div>

          {!canManage && mine && (
            <div className="flex flex-wrap justify-end gap-2 border-t pt-4">
              <Button variant="ghost" asChild><Link to={`/artist/history?assignment_id=${a.id}`}>My submissions</Link></Button>
              {!done && <Button variant="outline" onClick={() => setProgressOpen(true)}><Gauge />Update progress</Button>}
              {!done && <Button asChild><Link to={`/artist/submit?assignment=${a.id}`}><Send />Submit work</Link></Button>}
            </div>
          )}

          {canManage && (
            <div className="flex justify-between gap-2 border-t pt-4">
              <Button variant="ghost" className="text-destructive hover:text-destructive" onClick={() => setConfirmDelete(true)}><Trash2 />Delete</Button>
              <div className="flex gap-2">
                <Button variant="ghost" asChild><Link to={`/lead/submissions?assignment_id=${a.id}`}>Submissions</Link></Button>
                <Button variant="outline" onClick={() => setEditing(true)}><Pencil />Edit</Button>
                {a.status === "approved" && <Button loading={complete.isPending} onClick={() => complete.mutate(undefined)}><CheckCheck />Mark completed</Button>}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {editing && <AssignmentFormDialog open assignment={a} onOpenChange={(o) => { if (!o) setEditing(false) }} onSaved={onClose} />}
      {progressOpen && mine && <ProgressDialog assignmentId={a.id} current={mine.reported_progress_pct} note={mine.progress_note} onClose={() => setProgressOpen(false)} />}
      <ConfirmDialog
        open={confirmDelete} onOpenChange={setConfirmDelete} destructive loading={del.isPending}
        title="Delete this assignment?" confirmLabel="Delete"
        description="It will be removed from artists' task lists. The record is kept in the audit log."
        onConfirm={() => del.mutate(undefined)}
      />
    </>
  )
}

function ProgressDialog({ assignmentId, current, note, onClose }: { assignmentId: number; current: number; note: string | null; onClose: () => void }) {
  const [pct, setPct] = useState(current)
  const [text, setText] = useState(note ?? "")
  const save = useAction(() => api.put(`/assignments/${assignmentId}/progress`, { reported_progress_pct: pct, progress_note: text || null }), {
    success: "Progress updated", invalidate: WORK_KEYS, onSuccess: onClose,
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={(e) => { e.preventDefault(); save.mutate(undefined) }} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Update progress</DialogTitle>
            <DialogDescription>Your own estimate, so your lead can see how things are going. This does not submit or complete any scene.</DialogDescription>
          </DialogHeader>
          <Field label={`Progress: ${pct}%`} htmlFor="pg-pct">
            <input id="pg-pct" type="range" min={0} max={100} step={5} value={pct} onChange={(e) => setPct(Number(e.target.value))} className="w-full accent-[var(--primary)]" />
          </Field>
          <Field label="Note (optional)" htmlFor="pg-note">
            <Textarea id="pg-note" rows={2} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. SC01 rendered, SC02 in look-dev" />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending}>Save progress</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
