import { useState } from "react"
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom"
import { ArrowLeft, ClipboardList, FileUp, Lock, Pencil, Trash2 } from "lucide-react"

import { ErrorState, LoadingRows, PageHeader, ProjectStatusBadge } from "@/components/common"
import { EpisodeManager, ScreenplayImportModal } from "@/components/episode-manager"
import { ProjectFormDialog } from "@/components/project-form"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ConfirmDialog } from "@/components/ui/dialog"
import { EmptyState } from "@/components/common"
import { NativeSelect } from "@/components/ui/form-controls"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { formatDate, titleCase } from "@/lib/format"
import { useAction, useProject, useProjects } from "@/lib/queries"
import type { ProjectDetail } from "@/lib/types"

function ProjectSummary({ project: p, base }: { project: ProjectDetail; base: string }) {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [importScript, setImportScript] = useState(false)
  const del = useAction(() => api.del(`/projects/${p.id}`), {
    success: "Project deleted", invalidate: [["projects"], ["dashboard"]], onSuccess: () => navigate(`${base}/projects`),
  })
  return (
    <>
      <Card className="mb-6 p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-primary">{p.code}</span>
              <ProjectStatusBadge status={p.status} />
              {!p.can_manage && <span className="inline-flex items-center gap-1 text-xs text-muted-foreground"><Lock className="size-3" />View only</span>}
            </div>
            <h2 className="mt-1 text-lg font-semibold">{p.title}</h2>
            {p.description && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{p.description}</p>}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {p.can_manage && (
              <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setImportScript(true)}>
                <FileUp className="size-3.5 text-primary" />Upload Script…
              </Button>
            )}
            {p.can_manage && user?.role === "team_lead" && (
              <Button variant="outline" size="sm" asChild><Link to={`/lead/assignments?new=1`}><ClipboardList />Assign work</Link></Button>
            )}
            {p.can_manage && <Button variant="outline" size="sm" onClick={() => setEditing(true)}><Pencil />Edit</Button>}
            {p.can_manage && <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive" onClick={() => setDeleting(true)}><Trash2 /></Button>}
          </div>
        </div>
        <div className="mt-4 grid gap-4 border-t pt-4 text-sm sm:grid-cols-5">
          {[["Type", titleCase(p.project_type)], ["Team", p.team_name ?? "—"], ["Start", formatDate(p.start_date)],
            ["Expected completion", formatDate(p.expected_completion_date)], ["Scope", `${p.episode_count} ep · ${p.scene_count} scenes`]].map(([k, v]) => (
            <div key={k}><div className="text-[11px] uppercase tracking-wider text-muted-foreground">{k}</div><div className="mt-0.5">{v}</div></div>
          ))}
        </div>
      </Card>
      {editing && <ProjectFormDialog open project={p} onOpenChange={setEditing} />}
      {importScript && <ScreenplayImportModal project={p} onClose={() => setImportScript(false)} />}
      <ConfirmDialog open={deleting} onOpenChange={setDeleting} destructive loading={del.isPending} confirmLabel="Delete project"
        title={`Delete ${p.title}?`} description="The project will be archived and hidden. Assignment history is preserved in the database."
        onConfirm={() => del.mutate(undefined)} />
    </>
  )
}

export default function ProjectDetailPage() {
  const { id } = useParams()
  const { user } = useAuth()
  const base = user?.role === "admin" ? "/admin" : "/lead"
  const { data, isLoading, error, refetch } = useProject(Number(id))
  return (
    <>
      <Button variant="ghost" size="sm" asChild className="-ml-2 mb-3"><Link to={`${base}/projects`}><ArrowLeft />All projects</Link></Button>
      {error ? <ErrorState error={error} onRetry={refetch} /> : isLoading || !data ? <LoadingRows /> : (
        <>
          <ProjectSummary project={data} base={base} />
          <EpisodeManager project={data} />
        </>
      )}
    </>
  )
}

/** Lead "Episodes & Scenes" page: pick a project, manage its breakdown. */
export function EpisodesScenesPage() {
  const projects = useProjects()
  const [params, setParams] = useSearchParams()
  const manageable = (projects.data ?? []).filter((p) => p.can_manage)
  const selectedId = Number(params.get("project")) || manageable[0]?.id
  const project = useProject(selectedId)
  const [importScript, setImportScript] = useState(false)

  return (
    <>
      <PageHeader
        title="Episodes & scenes"
        description="Break productions down into episodes and scenes for assignment."
        actions={manageable.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setImportScript(true)}>
              <FileUp className="size-3.5 text-primary" />Upload Script / Screenplay…
            </Button>
            <NativeSelect className="w-72" value={selectedId ?? ""} onChange={(e) => setParams({ project: e.target.value })} aria-label="Project">
              {manageable.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.title}</option>)}
            </NativeSelect>
          </div>
        )}
      />
      {importScript && (
        <ScreenplayImportModal
          project={project.data}
          projectId={selectedId}
          onClose={() => setImportScript(false)}
        />
      )}
      {projects.isLoading ? <LoadingRows /> : manageable.length === 0 ? (
        <EmptyState title="No projects you can manage" description="Create a project for your team first."
          action={<Button asChild size="sm"><Link to="/lead/projects">Go to projects</Link></Button>} />
      ) : project.error ? <ErrorState error={project.error} onRetry={project.refetch} /> : !project.data ? <LoadingRows /> : (
        <EpisodeManager key={project.data.id} project={project.data} />
      )}
    </>
  )
}
