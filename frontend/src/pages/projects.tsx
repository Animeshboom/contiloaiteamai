import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { FileUp, Plus } from "lucide-react"

import { EmptyState, ErrorState, LoadingRows, PageHeader, ProjectStatusBadge } from "@/components/common"
import { ScreenplayImportModal } from "@/components/episode-manager"
import { ProjectFormDialog } from "@/components/project-form"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { NativeSelect } from "@/components/ui/form-controls"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAuth } from "@/lib/auth-context"
import { formatDate, titleCase } from "@/lib/format"
import { useProjects } from "@/lib/queries"
import type { ProjectStatus } from "@/lib/types"

export default function ProjectsPage() {
  const { user } = useAuth()
  const base = user?.role === "admin" ? "/admin" : "/lead"
  const navigate = useNavigate()
  const [status, setStatus] = useState<ProjectStatus | "">("")
  const [creating, setCreating] = useState(false)
  const [importing, setImporting] = useState(false)
  const { data, isLoading, error, refetch } = useProjects({ status: status || undefined })

  return (
    <>
      <PageHeader
        title="Projects"
        description="Films and series in production. Open a project to manage its episodes, scenes, and scripts."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" className="gap-1.5" onClick={() => setImporting(true)}>
              <FileUp className="size-4 text-primary" />Upload Script / Screenplay…
            </Button>
            <Button onClick={() => setCreating(true)}><Plus />New project</Button>
          </div>
        }
      />
      <div className="mb-4">
        <NativeSelect className="w-44" value={status} onChange={(e) => setStatus(e.target.value as ProjectStatus | "")} aria-label="Status filter">
          <option value="">All statuses</option>
          {(["planning", "active", "on_hold", "completed", "archived"] as ProjectStatus[]).map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
        </NativeSelect>
      </div>
      {error ? <ErrorState error={error} onRetry={refetch} /> : isLoading ? <LoadingRows /> : !data?.length ? (
        <EmptyState title="No projects" description="Create your first production or upload a shooting script to start assigning work."
          action={
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setImporting(true)}>
                <FileUp className="size-3.5 text-primary" />Upload Script / Screenplay
              </Button>
              <Button size="sm" onClick={() => setCreating(true)}><Plus />New project</Button>
            </div>
          } />
      ) : (
        <Card className="p-1">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Project</TableHead><TableHead>Type</TableHead><TableHead>Status</TableHead><TableHead>Team</TableHead>
                <TableHead className="text-right">Episodes</TableHead><TableHead className="text-right">Scenes</TableHead><TableHead>Timeline</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((p) => (
                <TableRow key={p.id} className="cursor-pointer" onClick={() => navigate(`${base}/projects/${p.id}`)}>
                  <TableCell>
                    <div className="font-mono text-[11px] text-muted-foreground">{p.code}</div>
                    <Link to={`${base}/projects/${p.id}`} className="font-medium hover:text-primary" onClick={(e) => e.stopPropagation()}>{p.title}</Link>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{titleCase(p.project_type)}</TableCell>
                  <TableCell><ProjectStatusBadge status={p.status} /></TableCell>
                  <TableCell className="text-xs">{p.team_name ?? "—"}</TableCell>
                  <TableCell className="text-right font-mono tabular">{p.episode_count}</TableCell>
                  <TableCell className="text-right font-mono tabular">{p.scene_count}</TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDate(p.start_date)} → {formatDate(p.expected_completion_date)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
      {creating && <ProjectFormDialog open onOpenChange={setCreating} onSaved={(p) => navigate(`${base}/projects/${p.id}`)} />}
      {importing && <ScreenplayImportModal onClose={() => setImporting(false)} />}
    </>
  )
}
