import { useState } from "react"
import { Pencil, Trash2 } from "lucide-react"

import { AssignmentFormDialog } from "@/components/assignment-form"
import { AssignmentStatusBadge, PriorityBadge, SceneChip } from "@/components/common"
import { Button } from "@/components/ui/button"
import { ConfirmDialog, Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"
import { formatDate, formatDateTime, relativeDeadline } from "@/lib/format"
import { useAction } from "@/lib/queries"
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
  const done = a.status === "approved" || a.status === "completed"
  const assignees = canManage ? a.assignees : a.assignees.filter((x) => x.user_id === viewerId)

  return (
    <>
      <Dialog open={!editing} onOpenChange={(o) => !o && onClose()}>
        <DialogContent wide>
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
            <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{canManage ? "Artists" : "Your progress"}</div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Artist</TableHead><TableHead>Status</TableHead>
                  <TableHead className="text-right">Reported</TableHead>
                  <TableHead className="text-right">Scenes submitted</TableHead>
                  <TableHead className="text-right">Scenes approved</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {assignees.map((x) => (
                  <TableRow key={x.id}>
                    <TableCell className="font-medium">{x.full_name}</TableCell>
                    <TableCell><AssignmentStatusBadge status={x.status} /></TableCell>
                    <TableCell className="text-right font-mono tabular" title="Artist self-reported progress — not an approval">{x.reported_progress_pct}%</TableCell>
                    <TableCell className="text-right font-mono tabular">{x.scenes_submitted}/{a.scenes.length}</TableCell>
                    <TableCell className="text-right font-mono tabular text-success">{x.scenes_approved}/{a.scenes.length}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="mt-2 text-[11px] text-muted-foreground">“Reported” is the artist's own estimate. Only lead-approved scenes count as complete.</p>
          </div>

          {canManage && (
            <div className="flex justify-between gap-2 border-t pt-4">
              <Button variant="ghost" className="text-destructive hover:text-destructive" onClick={() => setConfirmDelete(true)}><Trash2 />Delete</Button>
              <Button variant="outline" onClick={() => setEditing(true)}><Pencil />Edit</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {editing && <AssignmentFormDialog open assignment={a} onOpenChange={(o) => { if (!o) setEditing(false) }} onSaved={onClose} />}
      <ConfirmDialog
        open={confirmDelete} onOpenChange={setConfirmDelete} destructive loading={del.isPending}
        title="Delete this assignment?" confirmLabel="Delete"
        description="It will be removed from artists' task lists. The record is kept in the audit log."
        onConfirm={() => del.mutate(undefined)}
      />
    </>
  )
}
