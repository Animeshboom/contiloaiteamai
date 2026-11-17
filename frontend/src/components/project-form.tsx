import { useState, type FormEvent } from "react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Field, Input, NativeSelect, Textarea } from "@/components/ui/form-controls"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { titleCase } from "@/lib/format"
import { useAction, useTeams } from "@/lib/queries"
import type { Project, ProjectDetail, ProjectStatus, ProjectType } from "@/lib/types"

const TYPES: ProjectType[] = ["feature_film", "series", "short_film", "commercial", "music_video", "other"]
const STATUSES: ProjectStatus[] = ["planning", "active", "on_hold", "completed", "archived"]

export function ProjectFormDialog({ open, onOpenChange, project, onSaved }: {
  open: boolean; onOpenChange: (o: boolean) => void; project?: Project; onSaved?: (p: ProjectDetail) => void
}) {
  const { user } = useAuth()
  const teams = useTeams()
  const [code, setCode] = useState(project?.code ?? "")
  const [title, setTitle] = useState(project?.title ?? "")
  const [description, setDescription] = useState(project?.description ?? "")
  const [type, setType] = useState<ProjectType>(project?.project_type ?? "feature_film")
  const [status, setStatus] = useState<ProjectStatus>(project?.status ?? "active")
  const [start, setStart] = useState(project?.start_date ?? "")
  const [end, setEnd] = useState(project?.expected_completion_date ?? "")
  const [teamId, setTeamId] = useState<string>(project?.team_id ? String(project.team_id) : "")

  const body = {
    title, description: description || null, project_type: type, status,
    start_date: start || null, expected_completion_date: end || null,
    team_id: teamId ? Number(teamId) : null,
  }
  const save = useAction(
    () => project
      ? api.patch<ProjectDetail>(`/projects/${project.id}`, body)
      : api.post<ProjectDetail>("/projects", { ...body, code: code.toUpperCase() }),
    {
      success: project ? "Project updated" : "Project created",
      invalidate: [["projects"], ["project"], ["dashboard"]],
      onSuccess: (p) => { onSaved?.(p); onOpenChange(false) },
    },
  )

  function submit(e: FormEvent) {
    e.preventDefault()
    save.mutate(undefined)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{project ? "Edit project" : "New project"}</DialogTitle>
            <DialogDescription>A movie, series or other production. Episodes and scenes are added next.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Code" htmlFor="p-code" hint={!project ? "e.g. NEON-01" : undefined}>
              <Input id="p-code" required disabled={!!project} maxLength={32} pattern="[A-Za-z0-9][A-Za-z0-9_\-]*" className="font-mono uppercase"
                value={code} onChange={(e) => setCode(e.target.value)} />
            </Field>
            <Field label="Title" htmlFor="p-title" className="col-span-2">
              <Input id="p-title" required minLength={2} maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Type" htmlFor="p-type">
              <NativeSelect id="p-type" value={type} onChange={(e) => setType(e.target.value as ProjectType)}>
                {TYPES.map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Status" htmlFor="p-status">
              <NativeSelect id="p-status" value={status} onChange={(e) => setStatus(e.target.value as ProjectStatus)}>
                {STATUSES.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Start date" htmlFor="p-start"><Input id="p-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
            <Field label="Expected completion" htmlFor="p-end" error={start && end && end < start ? "Must be after the start date" : undefined}>
              <Input id="p-end" type="date" value={end} min={start || undefined} onChange={(e) => setEnd(e.target.value)} />
            </Field>
          </div>
          <Field label="Owning team" htmlFor="p-team" hint={user?.role === "team_lead" ? "Defaults to your team" : "Team leads of this team can manage it"}>
            <NativeSelect id="p-team" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
              <option value="">{user?.role === "team_lead" ? "My team" : "No team"}</option>
              {teams.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </NativeSelect>
          </Field>
          <Field label="Description" htmlFor="p-desc">
            <Textarea id="p-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" loading={save.isPending} disabled={!!(start && end && end < start)}>{project ? "Save" : "Create project"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
