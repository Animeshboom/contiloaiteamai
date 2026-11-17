import { useState, type FormEvent } from "react"
import { ChevronDown, ChevronRight, Pencil, Plus, Trash2 } from "lucide-react"

import { EmptyState, WorkStatusBadge } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ConfirmDialog, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Field, Input, NativeSelect, Textarea } from "@/components/ui/form-controls"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"
import { titleCase } from "@/lib/format"
import { useAction } from "@/lib/queries"
import type { Episode, ProjectDetail, Scene, WorkStatus } from "@/lib/types"

const WORK: WorkStatus[] = ["not_started", "in_progress", "in_review", "approved", "completed"]
const INVALIDATE = [["project"], ["projects"]]

/** Episodes → scenes tree for a project, with full CRUD when the viewer can manage it. */
export function EpisodeManager({ project }: { project: ProjectDetail }) {
  const [open, setOpen] = useState<Record<number, boolean>>(() => Object.fromEntries(project.episodes.slice(0, 1).map((e) => [e.id, true])))
  const [episodeDialog, setEpisodeDialog] = useState<{ episode?: Episode } | null>(null)
  const [sceneDialog, setSceneDialog] = useState<{ episode: Episode; scene?: Scene } | null>(null)
  const [bulkFor, setBulkFor] = useState<Episode | null>(null)
  const [deleting, setDeleting] = useState<{ kind: "episode" | "scene"; id: number; label: string } | null>(null)
  const manage = project.can_manage

  const del = useAction(() => api.del(`/${deleting!.kind === "episode" ? "episodes" : "scenes"}/${deleting!.id}`), {
    success: "Deleted", invalidate: INVALIDATE, onSuccess: () => setDeleting(null),
  })

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Episodes & scenes</h2>
        {manage && <Button size="sm" onClick={() => setEpisodeDialog({})}><Plus />Add episode</Button>}
      </div>

      {project.episodes.length === 0 ? (
        <EmptyState title="No episodes yet" description={manage ? "Add an episode (a feature film can be a single episode) and generate its scenes." : "This project has no episodes."}
          action={manage && <Button size="sm" onClick={() => setEpisodeDialog({})}><Plus />Add episode</Button>} />
      ) : project.episodes.map((ep) => (
        <Card key={ep.id}>
          <div className="flex items-center gap-2 px-3 py-2.5">
            <button type="button" className="flex flex-1 items-center gap-2 text-left cursor-pointer" onClick={() => setOpen({ ...open, [ep.id]: !open[ep.id] })} aria-expanded={!!open[ep.id]}>
              {open[ep.id] ? <ChevronDown className="size-4 text-muted-foreground" /> : <ChevronRight className="size-4 text-muted-foreground" />}
              <span className="font-mono text-xs text-primary">EP{String(ep.episode_number).padStart(2, "0")}</span>
              <span className="font-medium">{ep.title}</span>
              <span className="text-xs text-muted-foreground">· {ep.scenes.length} scene{ep.scenes.length === 1 ? "" : "s"}</span>
            </button>
            <WorkStatusBadge status={ep.status} />
            {manage && (
              <>
                <Button variant="ghost" size="icon" className="size-8" onClick={() => setEpisodeDialog({ episode: ep })} aria-label={`Edit episode ${ep.episode_number}`}><Pencil /></Button>
                <Button variant="ghost" size="icon" className="size-8 text-muted-foreground hover:text-destructive" aria-label={`Delete episode ${ep.episode_number}`}
                  onClick={() => setDeleting({ kind: "episode", id: ep.id, label: `EP${ep.episode_number} ${ep.title}` })}><Trash2 /></Button>
              </>
            )}
          </div>
          {open[ep.id] && (
            <div className="border-t px-2 pb-2">
              {ep.description && <p className="px-3 pt-3 text-xs text-muted-foreground">{ep.description}</p>}
              {ep.scenes.length > 0 && (
                <Table>
                  <TableHeader>
                    <TableRow><TableHead className="w-20">Scene</TableHead><TableHead>Title</TableHead><TableHead>Description</TableHead><TableHead>Status</TableHead>{manage && <TableHead className="w-20" />}</TableRow>
                  </TableHeader>
                  <TableBody>
                    {ep.scenes.map((s) => (
                      <TableRow key={s.id}>
                        <TableCell className="font-mono text-xs">{s.label}</TableCell>
                        <TableCell>{s.title ?? "—"}</TableCell>
                        <TableCell className="max-w-sm truncate text-xs text-muted-foreground">{s.description ?? ""}</TableCell>
                        <TableCell><WorkStatusBadge status={s.status} /></TableCell>
                        {manage && (
                          <TableCell className="text-right">
                            <Button variant="ghost" size="icon" className="size-7" onClick={() => setSceneDialog({ episode: ep, scene: s })} aria-label={`Edit ${s.label}`}><Pencil /></Button>
                            <Button variant="ghost" size="icon" className="size-7 text-muted-foreground hover:text-destructive" aria-label={`Delete ${s.label}`}
                              onClick={() => setDeleting({ kind: "scene", id: s.id, label: `${s.label} of EP${ep.episode_number}` })}><Trash2 /></Button>
                          </TableCell>
                        )}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
              {manage && (
                <div className="flex gap-2 px-2 pt-2">
                  <Button variant="outline" size="sm" onClick={() => setSceneDialog({ episode: ep })}><Plus />Add scene</Button>
                  <Button variant="ghost" size="sm" onClick={() => setBulkFor(ep)}>Add multiple…</Button>
                </div>
              )}
            </div>
          )}
        </Card>
      ))}

      {episodeDialog && <EpisodeDialog projectId={project.id} episode={episodeDialog.episode} nextNumber={Math.max(0, ...project.episodes.map((e) => e.episode_number)) + 1}
        onClose={() => setEpisodeDialog(null)} onCreated={(e) => setOpen({ ...open, [e.id]: true })} />}
      {sceneDialog && <SceneDialog {...sceneDialog} onClose={() => setSceneDialog(null)} />}
      {bulkFor && <BulkScenesDialog episode={bulkFor} onClose={() => setBulkFor(null)} />}
      <ConfirmDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)} destructive loading={del.isPending}
        title={`Delete ${deleting?.label}?`} confirmLabel="Delete"
        description="It will be hidden from the project and from new assignments. Existing assignment history is preserved."
        onConfirm={() => del.mutate(undefined)} />
    </div>
  )
}

function EpisodeDialog({ projectId, episode, nextNumber, onClose, onCreated }: {
  projectId: number; episode?: Episode; nextNumber: number; onClose: () => void; onCreated: (e: Episode) => void
}) {
  const [num, setNum] = useState(episode?.episode_number ?? nextNumber)
  const [title, setTitle] = useState(episode?.title ?? "")
  const [description, setDescription] = useState(episode?.description ?? "")
  const [status, setStatus] = useState<WorkStatus>(episode?.status ?? "not_started")
  const [sceneCount, setSceneCount] = useState(0)
  const save = useAction(
    () => episode
      ? api.patch<Episode>(`/episodes/${episode.id}`, { episode_number: num, title, description: description || null, status })
      : api.post<Episode>(`/projects/${projectId}/episodes`, { episode_number: num, title, description: description || null, scene_count: sceneCount }),
    { success: episode ? "Episode updated" : "Episode created", invalidate: INVALIDATE, onSuccess: (e) => { if (!episode) onCreated(e); onClose() } },
  )
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(undefined) }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader><DialogTitle>{episode ? "Edit episode" : "Add episode"}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-4 gap-3">
            <Field label="Number" htmlFor="e-num"><Input id="e-num" type="number" min={1} required value={num} onChange={(e) => setNum(Number(e.target.value))} /></Field>
            <Field label="Title" htmlFor="e-title" className="col-span-3"><Input id="e-title" required value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
          </div>
          {episode ? (
            <Field label="Status" htmlFor="e-status">
              <NativeSelect id="e-status" value={status} onChange={(e) => setStatus(e.target.value as WorkStatus)}>
                {WORK.map((w) => <option key={w} value={w}>{titleCase(w)}</option>)}
              </NativeSelect>
            </Field>
          ) : (
            <Field label="Generate scenes" htmlFor="e-scenes" hint="Creates SC01…SCnn. You can add or edit scenes later.">
              <Input id="e-scenes" type="number" min={0} max={200} value={sceneCount} onChange={(e) => setSceneCount(Number(e.target.value))} />
            </Field>
          )}
          <Field label="Description" htmlFor="e-desc"><Textarea id="e-desc" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending}>{episode ? "Save" : "Add episode"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function SceneDialog({ episode, scene, onClose }: { episode: Episode; scene?: Scene; onClose: () => void }) {
  const [num, setNum] = useState(scene?.scene_number ?? Math.max(0, ...episode.scenes.map((s) => s.scene_number)) + 1)
  const [title, setTitle] = useState(scene?.title ?? "")
  const [description, setDescription] = useState(scene?.description ?? "")
  const [status, setStatus] = useState<WorkStatus>(scene?.status ?? "not_started")
  const save = useAction(
    () => scene
      ? api.patch(`/scenes/${scene.id}`, { scene_number: num, title: title || null, description: description || null, status })
      : api.post(`/episodes/${episode.id}/scenes`, { scene_number: num, title: title || null, description: description || null }),
    { success: scene ? "Scene updated" : "Scene added", invalidate: INVALIDATE, onSuccess: onClose },
  )
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(undefined) }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{scene ? `Edit ${scene.label}` : "Add scene"}</DialogTitle>
            <DialogDescription>EP{String(episode.episode_number).padStart(2, "0")} — {episode.title}</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-4 gap-3">
            <Field label="Number" htmlFor="s-num"><Input id="s-num" type="number" min={1} required value={num} onChange={(e) => setNum(Number(e.target.value))} /></Field>
            <Field label="Title" htmlFor="s-title" className="col-span-3"><Input id="s-title" value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
          </div>
          {scene && (
            <Field label="Status" htmlFor="s-status">
              <NativeSelect id="s-status" value={status} onChange={(e) => setStatus(e.target.value as WorkStatus)}>
                {WORK.map((w) => <option key={w} value={w}>{titleCase(w)}</option>)}
              </NativeSelect>
            </Field>
          )}
          <Field label="Description / shot notes" htmlFor="s-desc"><Textarea id="s-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending}>{scene ? "Save" : "Add scene"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function BulkScenesDialog({ episode, onClose }: { episode: Episode; onClose: () => void }) {
  const [count, setCount] = useState(5)
  const next = Math.max(0, ...episode.scenes.map((s) => s.scene_number)) + 1
  const save = useAction(() => api.post(`/episodes/${episode.id}/scenes/bulk`, { count }), {
    success: `${count} scenes added`, invalidate: INVALIDATE, onSuccess: onClose,
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={(e) => { e.preventDefault(); save.mutate(undefined) }} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Add multiple scenes</DialogTitle>
            <DialogDescription>Scenes will be numbered SC{String(next).padStart(2, "0")} to SC{String(next + count - 1).padStart(2, "0")}.</DialogDescription>
          </DialogHeader>
          <Field label="How many?" htmlFor="b-count"><Input id="b-count" type="number" min={1} max={200} value={count} onChange={(e) => setCount(Number(e.target.value))} /></Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending}>Add scenes</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
