import { useEffect, useMemo, useState, type FormEvent } from "react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Checkbox, Field, Input, NativeSelect, Textarea } from "@/components/ui/form-controls"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { isoToStudioLocal, studioLocalToIso, titleCase } from "@/lib/format"
import { useAction, useProject, useProjects, useUsers } from "@/lib/queries"
import type { Assignment, Priority } from "@/lib/types"
import { cn } from "@/lib/utils"

const PRIORITIES: Priority[] = ["low", "medium", "high", "urgent"]

/** Create (no `assignment`) or edit an assignment. */
export function AssignmentFormDialog({ open, onOpenChange, assignment, onSaved }: {
  open: boolean; onOpenChange: (o: boolean) => void; assignment?: Assignment; onSaved?: (a: Assignment) => void
}) {
  const editing = !!assignment
  const { config } = useAuth()
  const projects = useProjects({ status: "active" })
  const artists = useUsers({ role: "artist" })

  const [projectId, setProjectId] = useState<number | undefined>(assignment?.project_id)
  const [episodeId, setEpisodeId] = useState<number | undefined>(assignment?.episode_id ?? undefined)
  const [sceneIds, setSceneIds] = useState<number[]>(assignment?.scenes.map((s) => s.id) ?? [])
  const [artistIds, setArtistIds] = useState<number[]>(assignment?.assignees.map((x) => x.user_id) ?? [])
  const [title, setTitle] = useState(assignment?.title ?? "")
  const [description, setDescription] = useState(assignment?.description ?? "")
  const [deliverables, setDeliverables] = useState(assignment?.expected_deliverables ?? "")
  const [priority, setPriority] = useState<Priority>(assignment?.priority ?? "medium")
  const defaultDeadline = config ? `${config.studio_today}T${String(config.eod_deadline_hour).padStart(2, "0")}:00` : ""
  const [deadline, setDeadline] = useState(assignment ? isoToStudioLocal(assignment.deadline) : defaultDeadline)

  const project = useProject(projectId)
  const manageable = (projects.data ?? []).filter((p) => p.can_manage)
  const episode = project.data?.episodes.find((e) => e.id === episodeId)

  useEffect(() => {
    if (!editing && !projectId && manageable.length === 1) setProjectId(manageable[0].id)
  }, [editing, projectId, manageable])

  const allScenesSelected = !!episode && episode.scenes.length > 0 && episode.scenes.every((s) => sceneIds.includes(s.id))
  const toggle = (list: number[], id: number) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id])
  const valid = !!projectId && artistIds.length > 0 && (sceneIds.length > 0 || description.trim() || deliverables.trim())

  const create = useAction(
    () => api.post<Assignment>("/assignments", {
      project_id: projectId, episode_id: episodeId ?? null, scene_ids: sceneIds, artist_ids: artistIds,
      title: title.trim() || null, description: description || null, expected_deliverables: deliverables || null,
      priority, deadline: deadline ? studioLocalToIso(deadline) : null,
    }),
    { success: "Assignment created", invalidate: [["assignments"], ["dashboard"], ["projects"]], onSuccess: (a) => { onSaved?.(a); onOpenChange(false) } },
  )

  const original = useMemo(() => new Set(assignment?.assignees.map((x) => x.user_id) ?? []), [assignment])
  const update = useAction(
    () => api.patch<Assignment>(`/assignments/${assignment!.id}`, {
      title: title.trim() || undefined, description, expected_deliverables: deliverables, priority,
      deadline: studioLocalToIso(deadline),
      add_artist_ids: artistIds.filter((id) => !original.has(id)),
      remove_artist_ids: [...original].filter((id) => !artistIds.includes(id)),
    }),
    { success: "Assignment updated", invalidate: [["assignments"], ["dashboard"]], onSuccess: (a) => { onSaved?.(a); onOpenChange(false) } },
  )

  function submit(e: FormEvent) {
    e.preventDefault()
    if (editing) update.mutate(undefined)
    else create.mutate(undefined)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent wide>
        <form onSubmit={submit} className="grid gap-5">
          <DialogHeader>
            <DialogTitle>{editing ? "Edit assignment" : "New assignment"}</DialogTitle>
            <DialogDescription>
              {editing ? "Scope (project and scenes) is fixed once created. Deadline, priority, details and artists can change."
                : "Assign scenes from an episode, a whole episode, or a non-scene deliverable. Each artist's progress is tracked separately."}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Project" htmlFor="a-project">
              <NativeSelect id="a-project" required disabled={editing} value={projectId ?? ""}
                onChange={(e) => { setProjectId(Number(e.target.value) || undefined); setEpisodeId(undefined); setSceneIds([]) }}>
                <option value="">Select project…</option>
                {(editing ? projects.data ?? [] : manageable).map((p) => <option key={p.id} value={p.id}>{p.code} — {p.title}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Episode" htmlFor="a-episode" hint={!editing && projectId && !project.data?.episodes.length ? "This project has no episodes yet" : undefined}>
              <NativeSelect id="a-episode" disabled={editing || !project.data} value={episodeId ?? ""}
                onChange={(e) => { setEpisodeId(Number(e.target.value) || undefined); setSceneIds([]) }}>
                <option value="">{editing ? assignment?.episode_title ?? "No episode" : "No specific episode"}</option>
                {project.data?.episodes.map((ep) => <option key={ep.id} value={ep.id}>EP{String(ep.episode_number).padStart(2, "0")} — {ep.title}</option>)}
              </NativeSelect>
            </Field>
          </div>

          {!editing && episode && (
            <Field label={`Scenes (${sceneIds.length} selected)`}>
              {episode.scenes.length === 0 ? <p className="text-xs text-muted-foreground">No scenes in this episode.</p> : (
                <div className="rounded-md border p-3">
                  <label className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
                    <Checkbox checked={allScenesSelected} onCheckedChange={(c) => setSceneIds(c ? episode.scenes.map((s) => s.id) : [])} />
                    Entire episode
                  </label>
                  <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-6">
                    {episode.scenes.map((s) => {
                      const on = sceneIds.includes(s.id)
                      return (
                        <button type="button" key={s.id} onClick={() => setSceneIds(toggle(sceneIds, s.id))} title={s.title ?? s.label}
                          aria-pressed={on}
                          className={cn("rounded-md border px-2 py-1.5 font-mono text-xs transition-colors cursor-pointer",
                            on ? "border-primary bg-primary/15 text-primary" : "hover:bg-accent text-muted-foreground")}>
                          {s.label}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}
            </Field>
          )}
          {editing && assignment!.scenes.length > 0 && (
            <p className="text-xs text-muted-foreground">Scenes: {assignment!.scenes.map((s) => s.label).join(", ")}</p>
          )}

          <Field label={`Artists (${artistIds.length} selected)`}>
            {artists.data?.length === 0 ? <p className="text-xs text-muted-foreground">No artists in your team.</p> : (
              <div className="grid max-h-40 gap-1 overflow-y-auto rounded-md border p-2 sm:grid-cols-2">
                {artists.data?.map((u) => (
                  <label key={u.id} className="flex items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-accent cursor-pointer">
                    <Checkbox checked={artistIds.includes(u.id)} onCheckedChange={() => setArtistIds(toggle(artistIds, u.id))} />
                    <span className="truncate">{u.full_name}</span>
                    <span className="ml-auto truncate text-xs text-muted-foreground">{u.job_title}</span>
                  </label>
                ))}
              </div>
            )}
          </Field>

          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Deadline (studio time)" htmlFor="a-deadline" className="sm:col-span-2" hint={!editing ? `Defaults to today's EOD (${config?.eod_deadline_hour}:00)` : undefined}>
              <Input id="a-deadline" type="datetime-local" required value={deadline} onChange={(e) => setDeadline(e.target.value)} />
            </Field>
            <Field label="Priority" htmlFor="a-priority">
              <NativeSelect id="a-priority" value={priority} onChange={(e) => setPriority(e.target.value as Priority)}>
                {PRIORITIES.map((p) => <option key={p} value={p}>{titleCase(p)}</option>)}
              </NativeSelect>
            </Field>
          </div>

          <Field label="Title" htmlFor="a-title" hint={!editing ? "Leave blank to generate from the episode and scenes" : undefined}>
            <Input id="a-title" maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Task description" htmlFor="a-desc">
              <Textarea id="a-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What needs to be done" />
            </Field>
            <Field label="Expected deliverables" htmlFor="a-deliv">
              <Textarea id="a-deliv" rows={3} value={deliverables} onChange={(e) => setDeliverables(e.target.value)} placeholder="e.g. 1080p MP4 per scene, 24fps" />
            </Field>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={!valid} loading={create.isPending || update.isPending}>{editing ? "Save changes" : "Create assignment"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
