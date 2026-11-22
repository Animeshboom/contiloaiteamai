import { useState, useMemo, type FormEvent } from "react"
import {
  ChevronDown, ChevronRight, Clock, ExternalLink, Eye, FileText, FileUp,
  FolderOpen, Pencil, Plus, Sparkles, Trash2, Upload, Users, Video
} from "lucide-react"
import { toast } from "sonner"

import { EmptyState, WorkStatusBadge } from "@/components/common"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  ConfirmDialog, Dialog, DialogContent, DialogDescription,
  DialogFooter, DialogHeader, DialogTitle
} from "@/components/ui/dialog"
import { Checkbox, Field, Input, NativeSelect, Textarea } from "@/components/ui/form-controls"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, errorMessage } from "@/lib/api"
import { formatDuration, titleCase } from "@/lib/format"
import { useAction, useProjects } from "@/lib/queries"
import { CHOTA_TENALI_EPISODE_1_SCRIPT } from "@/lib/chota-tenali-sample"
import type { Episode, Project, ProjectDetail, Scene, WorkStatus } from "@/lib/types"
import { cn } from "@/lib/utils"

const WORK: WorkStatus[] = ["not_started", "in_progress", "in_review", "approved", "completed"]
const INVALIDATE = [["project"], ["projects"], ["assignments"], ["submissions"]]

export function EpisodeManager({ project }: { project: ProjectDetail }) {
  const [open, setOpen] = useState<Record<number, boolean>>(() =>
    Object.fromEntries(project.episodes.slice(0, 1).map((e) => [e.id, true]))
  )
  const [episodeDialog, setEpisodeDialog] = useState<{ episode?: Episode } | null>(null)
  const [sceneDialog, setSceneDialog] = useState<{ episode: Episode; scene?: Scene } | null>(null)
  const [bulkFor, setBulkFor] = useState<Episode | null>(null)
  const [importFor, setImportFor] = useState<Episode | null>(null)
  const [importForProject, setImportForProject] = useState(false)
  const [readerScene, setReaderScene] = useState<{ episode: Episode; scene: Scene } | null>(null)
  const [deleting, setDeleting] = useState<{ kind: "episode" | "scene"; id: number; label: string } | null>(null)
  const manage = project.can_manage

  const del = useAction(() => api.del(`/${deleting!.kind === "episode" ? "episodes" : "scenes"}/${deleting!.id}`), {
    success: "Deleted", invalidate: INVALIDATE, onSuccess: () => setDeleting(null),
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">Episodes &amp; Scene Breakdown</h2>
          <p className="text-xs text-muted-foreground">Manage episode screenplays, 22-minute runtime targets, and Google Drive links.</p>
        </div>
        {manage && (
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setImportForProject(true)}>
              <FileUp className="size-3.5 text-primary" />Upload Script / Screenplay…
            </Button>
            <Button size="sm" onClick={() => setEpisodeDialog({})}><Plus />Add episode</Button>
          </div>
        )}
      </div>

      {project.episodes.length === 0 ? (
        <EmptyState
          title="No episodes yet"
          description={manage ? "Upload your shooting screenplay (.docx, .txt) to automatically generate all 22 scenes, or add an episode manually." : "This project has no episodes."}
          action={manage && (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" onClick={() => setImportForProject(true)}>
                <FileUp className="size-3.5" />Upload Script / Screenplay
              </Button>
              <Button size="sm" variant="outline" onClick={() => setEpisodeDialog({})}>
                <Plus />Add episode
              </Button>
            </div>
          )}
        />
      ) : project.episodes.map((ep) => {
        const totalSec = ep.scenes.reduce((acc, s) => acc + (s.duration_sec || 0), 0)
        const approvedSec = ep.scenes
          .filter((s) => s.status === "approved" || s.status === "completed")
          .reduce((acc, s) => acc + (s.duration_sec || 0), 0)
        const approvedPct = totalSec > 0 ? Math.round((approvedSec / totalSec) * 100) : 0
        const approvedCount = ep.scenes.filter((s) => s.status === "approved" || s.status === "completed").length
        const inProgressCount = ep.scenes.filter((s) => s.status === "in_progress" || s.status === "in_review").length

        return (
          <Card key={ep.id} className="overflow-hidden">
            <div className="flex flex-wrap items-center gap-2 px-3 py-2.5">
              <button
                type="button"
                className="flex flex-1 items-center gap-2 text-left cursor-pointer"
                onClick={() => setOpen({ ...open, [ep.id]: !open[ep.id] })}
                aria-expanded={!!open[ep.id]}
              >
                {open[ep.id] ? <ChevronDown className="size-4 text-muted-foreground" /> : <ChevronRight className="size-4 text-muted-foreground" />}
                <span className="font-mono text-xs font-semibold text-primary">EP{String(ep.episode_number).padStart(2, "0")}</span>
                <span className="font-medium text-foreground">{ep.title}</span>
                <span className="text-xs text-muted-foreground">· {ep.scenes.length} scene{ep.scenes.length === 1 ? "" : "s"}</span>
                {totalSec > 0 && (
                  <span className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[11px] font-medium text-primary">
                    {formatDuration(totalSec)}
                  </span>
                )}
              </button>
              <WorkStatusBadge status={ep.status} />
              {manage && (
                <div className="flex items-center gap-1">
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8 gap-1.5 text-xs"
                    onClick={() => setImportFor(ep)}
                  >
                    <FileText className="size-3.5 text-primary" />Import Screenplay
                  </Button>
                  <Button variant="ghost" size="icon" className="size-8" onClick={() => setEpisodeDialog({ episode: ep })} aria-label={`Edit episode ${ep.episode_number}`}>
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-8 text-muted-foreground hover:text-destructive"
                    aria-label={`Delete episode ${ep.episode_number}`}
                    onClick={() => setDeleting({ kind: "episode", id: ep.id, label: `EP${ep.episode_number} ${ep.title}` })}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              )}
            </div>

            {/* 22-Minute Runtime Progress Tracker */}
            {ep.scenes.length > 0 && (
              <div className="border-t bg-muted/20 px-3 py-2 text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Clock className="size-3.5 text-primary" />
                    <span className="font-medium text-foreground">Runtime Tracker:</span>
                    <span className="font-mono font-bold text-success">{formatDuration(approvedSec)}</span>
                    <span className="text-muted-foreground">/ {formatDuration(totalSec || 1320)} approved ({approvedPct}%)</span>
                  </div>
                  <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                    <span className="text-success font-medium">{approvedCount} approved</span>
                    <span>·</span>
                    <span className="text-primary font-medium">{inProgressCount} in progress</span>
                    <span>·</span>
                    <span>{ep.scenes.length - approvedCount - inProgressCount} pending</span>
                  </div>
                </div>
                <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full bg-gradient-to-r from-primary to-success transition-all duration-300"
                    style={{ width: `${Math.min(100, approvedPct)}%` }}
                  />
                </div>
              </div>
            )}

            {open[ep.id] && (
              <div className="border-t px-2 pb-2">
                {ep.description && <p className="px-3 pt-3 text-xs text-muted-foreground">{ep.description}</p>}
                {ep.scenes.length > 0 ? (
                  <Table className="mt-2">
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-16">Scene</TableHead>
                        <TableHead>Title &amp; Setting</TableHead>
                        <TableHead className="w-24">Duration</TableHead>
                        <TableHead className="hidden md:table-cell">Cast</TableHead>
                        <TableHead className="w-28">Drive Link</TableHead>
                        <TableHead className="w-24">Status</TableHead>
                        <TableHead className="w-24 text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {ep.scenes.map((s) => {
                        const driveLink = s.reference_links?.find((l) =>
                          l.url?.includes("drive.google.com") || l.label?.toLowerCase().includes("drive")
                        )?.url || s.reference_links?.[0]?.url

                        return (
                          <TableRow key={s.id} className="hover:bg-muted/40 transition-colors">
                            <TableCell className="font-mono text-xs font-semibold text-primary">{s.label}</TableCell>
                            <TableCell>
                              <button
                                type="button"
                                className="text-left font-medium hover:underline text-foreground cursor-pointer"
                                onClick={() => setReaderScene({ episode: ep, scene: s })}
                              >
                                {s.title ?? "—"}
                              </button>
                              {s.description && (
                                <p className="mt-0.5 line-clamp-1 text-[11px] text-muted-foreground">
                                  {s.description}
                                </p>
                              )}
                            </TableCell>
                            <TableCell className="font-mono text-xs">
                              {s.duration_sec != null ? (
                                <span className="inline-flex items-center gap-1 text-muted-foreground">
                                  <Clock className="size-3 text-primary" />
                                  {formatDuration(s.duration_sec)}
                                </span>
                              ) : "—"}
                            </TableCell>
                            <TableCell className="hidden md:table-cell">
                              {s.characters && s.characters.length > 0 ? (
                                <div className="flex flex-wrap gap-1">
                                  {s.characters.slice(0, 3).map((c) => (
                                    <span key={c} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                                      {c}
                                    </span>
                                  ))}
                                  {s.characters.length > 3 && (
                                    <span className="text-[10px] text-muted-foreground">+{s.characters.length - 3}</span>
                                  )}
                                </div>
                              ) : <span className="text-xs text-muted-foreground">—</span>}
                            </TableCell>
                            <TableCell>
                              {driveLink ? (
                                <a
                                  href={driveLink}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 rounded bg-blue-500/10 px-2 py-0.5 text-xs font-medium text-blue-400 hover:bg-blue-500/20 hover:underline"
                                  title={driveLink}
                                >
                                  <FolderOpen className="size-3" />Drive ↗
                                </a>
                              ) : (
                                <span className="text-xs text-muted-foreground">—</span>
                              )}
                            </TableCell>
                            <TableCell><WorkStatusBadge status={s.status} /></TableCell>
                            <TableCell className="text-right">
                              <div className="flex items-center justify-end gap-1">
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="size-7"
                                  title="View Screenplay"
                                  onClick={() => setReaderScene({ episode: ep, scene: s })}
                                >
                                  <Eye className="size-3.5" />
                                </Button>
                                {manage && (
                                  <>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="size-7"
                                      title="Edit Scene"
                                      onClick={() => setSceneDialog({ episode: ep, scene: s })}
                                    >
                                      <Pencil className="size-3.5" />
                                    </Button>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="size-7 text-muted-foreground hover:text-destructive"
                                      title="Delete Scene"
                                      onClick={() => setDeleting({ kind: "scene", id: s.id, label: `${s.label} of EP${ep.episode_number}` })}
                                    >
                                      <Trash2 className="size-3.5" />
                                    </Button>
                                  </>
                                )}
                              </div>
                            </TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                ) : (
                  <div className="py-6 text-center text-xs text-muted-foreground">
                    No scenes in this episode yet. Import a shooting script or add scenes manually.
                  </div>
                )}
                {manage && (
                  <div className="flex flex-wrap items-center gap-2 px-2 pt-3">
                    <Button variant="outline" size="sm" onClick={() => setImportFor(ep)}>
                      <FileText className="size-3.5" />Import Screenplay…
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => setSceneDialog({ episode: ep })}>
                      <Plus className="size-3.5" />Add scene
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setBulkFor(ep)}>
                      Add multiple…
                    </Button>
                  </div>
                )}
              </div>
            )}
          </Card>
        )
      })}

      {episodeDialog && (
        <EpisodeDialog
          projectId={project.id}
          episode={episodeDialog.episode}
          nextNumber={Math.max(0, ...project.episodes.map((e) => e.episode_number)) + 1}
          onClose={() => setEpisodeDialog(null)}
          onCreated={(e) => setOpen({ ...open, [e.id]: true })}
        />
      )}
      {sceneDialog && <SceneDialog {...sceneDialog} onClose={() => setSceneDialog(null)} />}
      {bulkFor && <BulkScenesDialog episode={bulkFor} onClose={() => setBulkFor(null)} />}
      {importFor && <ScreenplayImportModal episode={importFor} onClose={() => setImportFor(null)} />}
      {importForProject && <ScreenplayImportModal project={project} onClose={() => setImportForProject(false)} />}
      {readerScene && (
        <ScreenplayReaderModal
          episode={readerScene.episode}
          scene={readerScene.scene}
          canManage={manage}
          onClose={() => setReaderScene(null)}
          onEdit={() => {
            const sc = readerScene
            setReaderScene(null)
            setSceneDialog(sc)
          }}
        />
      )}
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        destructive
        loading={del.isPending}
        title={`Delete ${deleting?.label}?`}
        confirmLabel="Delete"
        description="It will be hidden from the project and from new assignments. Existing assignment history is preserved."
        onConfirm={() => del.mutate(undefined)}
      />
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
            <Field label="Generate scenes" htmlFor="e-scenes" hint="Creates SC01…SCnn. You can also import a shooting script later.">
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
  const [durationSec, setDurationSec] = useState<string>(scene?.duration_sec != null ? String(scene.duration_sec) : "")
  const existingDrive = scene?.reference_links?.find((l) => l.url?.includes("drive.google.com") || l.label === "Google Drive")?.url ?? ""
  const [driveUrl, setDriveUrl] = useState<string>(existingDrive)

  const save = useAction(
    () => {
      const dur = durationSec.trim() ? Number(durationSec) : null
      const refLinks = driveUrl.trim()
        ? [{ label: "Google Drive", url: driveUrl.trim() }]
        : (scene?.reference_links || [])

      return scene
        ? api.patch(`/scenes/${scene.id}`, {
            scene_number: num,
            title: title || null,
            description: description || null,
            status,
            duration_sec: dur,
            reference_links: refLinks,
          })
        : api.post(`/episodes/${episode.id}/scenes`, {
            scene_number: num,
            title: title || null,
            description: description || null,
            duration_sec: dur,
            reference_links: refLinks,
          })
    },
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
            <Field label="Number" htmlFor="s-num">
              <Input id="s-num" type="number" min={1} required value={num} onChange={(e) => setNum(Number(e.target.value))} />
            </Field>
            <Field label="Title / Heading" htmlFor="s-title" className="col-span-3">
              <Input id="s-title" placeholder="e.g. EXT. VILLAGE / MARKET — MORNING" value={title} onChange={(e) => setTitle(e.target.value)} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Duration (seconds)" htmlFor="s-dur" hint={durationSec ? `Approx ${formatDuration(Number(durationSec))}` : undefined}>
              <Input id="s-dur" type="number" step="any" min={0} placeholder="e.g. 75 for 01:15" value={durationSec} onChange={(e) => setDurationSec(e.target.value)} />
            </Field>
            {scene ? (
              <Field label="Status" htmlFor="s-status">
                <NativeSelect id="s-status" value={status} onChange={(e) => setStatus(e.target.value as WorkStatus)}>
                  {WORK.map((w) => <option key={w} value={w}>{titleCase(w)}</option>)}
                </NativeSelect>
              </Field>
            ) : <div />}
          </div>
          <Field label="Google Drive Reference / Playblast URL" htmlFor="s-drive" hint="Folder, Animatic, or Playblast link">
            <Input id="s-drive" type="url" placeholder="https://drive.google.com/…" value={driveUrl} onChange={(e) => setDriveUrl(e.target.value)} />
          </Field>
          <Field label="Screenplay Text / Shot Notes" htmlFor="s-desc">
            <Textarea id="s-desc" rows={4} placeholder="Hindi dialogue, action lines, camera angles, [AI / CONTINUITY] notes…" value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>
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

interface ParsedScenePreview {
  scene_number: number
  title?: string
  description?: string
  duration_sec?: number | null
  characters: string[]
}

export interface ScreenplayImportModalProps {
  episode?: Episode | null
  project?: ProjectDetail | Project | null
  projectId?: number
  onClose: () => void
  onSuccess?: () => void
}

export function ScreenplayImportModal({
  episode,
  project,
  projectId: explicitProjectId,
  onClose,
  onSuccess,
}: ScreenplayImportModalProps) {
  const projectsQuery = useProjects()
  const availableProjects = useMemo(() => (projectsQuery.data ?? []).filter((p) => p.can_manage), [projectsQuery.data])

  const initialProjectId = episode ? undefined : (project?.id ?? explicitProjectId ?? availableProjects[0]?.id)
  const [selectedProjectId, setSelectedProjectId] = useState<number | undefined>(initialProjectId)
  const [scriptText, setScriptText] = useState("")
  const [replaceExisting, setReplaceExisting] = useState(true)
  const [parsed, setParsed] = useState<ParsedScenePreview[]>([])
  const [parsing, setParsing] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [fileName, setFileName] = useState<string | null>(null)
  const [dragActive, setDragActive] = useState(false)

  const activeProjectId = episode ? undefined : (project?.id ?? explicitProjectId ?? selectedProjectId ?? availableProjects[0]?.id)

  const parseAction = async (text: string) => {
    if (!text.trim()) {
      setParsed([])
      return
    }
    setParsing(true)
    try {
      const res = await api.post<ParsedScenePreview[]>("/screenplay/parse", { raw_text: text })
      setParsed(res)
    } catch {
      setParsed([])
    } finally {
      setParsing(false)
    }
  }

  const handleProcessFile = async (file: File) => {
    if (!file) return
    setUploading(true)
    setFileName(file.name)
    try {
      const res = await api.upload<{
        filename: string
        raw_text: string
        scenes: ParsedScenePreview[]
        scene_count: number
      }>("/screenplay/upload-file", file)
      setScriptText(res.raw_text)
      setParsed(res.scenes)
      toast.success(`Parsed ${res.scene_count} scenes from ${file.name}`)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setUploading(false)
    }
  }

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleProcessFile(file)
    e.target.value = ""
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleProcessFile(file)
  }

  const handleLoadSample = () => {
    setFileName("Chota Tenali Ep 1 (Sample Script)")
    setScriptText(CHOTA_TENALI_EPISODE_1_SCRIPT)
    parseAction(CHOTA_TENALI_EPISODE_1_SCRIPT)
  }

  const importAction = useAction(
    () => {
      if (episode?.id) {
        return api.post(`/episodes/${episode.id}/scenes/screenplay-import`, {
          raw_text: scriptText,
          replace_existing: replaceExisting,
        })
      }
      if (!activeProjectId) {
        throw new Error("Please select a project to import scenes into.")
      }
      return api.post(`/projects/${activeProjectId}/screenplay-import`, {
        raw_text: scriptText,
        replace_existing: replaceExisting,
      })
    },
    {
      success: episode
        ? `Imported ${parsed.length || "all"} scenes into EP${String(episode.episode_number).padStart(2, "0")}`
        : `Imported ${parsed.length || "all"} scenes into project!`,
      invalidate: INVALIDATE,
      onSuccess: () => {
        onSuccess?.()
        onClose()
      },
    }
  )

  const totalDuration = useMemo(() => {
    return parsed.reduce((sum, s) => sum + (s.duration_sec || 0), 0)
  }, [parsed])

  const allCharacters = useMemo(() => {
    const set = new Set<string>()
    parsed.forEach((s) => s.characters.forEach((c) => set.add(c)))
    return Array.from(set)
  }, [parsed])

  const currentProjectObj = project ?? availableProjects.find((p) => p.id === activeProjectId)

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[92vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileUp className="size-5 text-primary" />
            {episode
              ? `Import Screenplay into EP${String(episode.episode_number).padStart(2, "0")} — ${episode.title}`
              : currentProjectObj
                ? `Upload & Import Script — ${currentProjectObj.title} (${currentProjectObj.code})`
                : "Upload & Import Screenplay Script"}
          </DialogTitle>
          <DialogDescription>
            Upload a shooting script document (.docx, .txt, .fountain, .md) or paste script text.
            StudioTrack AI automatically extracts all 22 scenes, durations (`mm:ss`), characters, dialogues, and continuity notes.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-4 py-2 pr-1">
          {/* Target project selector if not pre-bound */}
          {!episode && !project && !explicitProjectId && (
            <div className="rounded-lg border bg-muted/40 p-3 space-y-1.5">
              <label htmlFor="target-proj-select" className="text-xs font-semibold text-foreground">Target Project</label>
              <NativeSelect
                id="target-proj-select"
                value={activeProjectId ?? ""}
                onChange={(e) => setSelectedProjectId(Number(e.target.value))}
                className="w-full"
              >
                {availableProjects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.code} — {p.title}
                  </option>
                ))}
              </NativeSelect>
              <p className="text-[11px] text-muted-foreground">
                Scenes will be imported into Episode 01 of the selected project (auto-creates Episode 01 if needed).
              </p>
            </div>
          )}

          {/* Drag & Drop File Upload Area */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragActive(true) }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
            className={cn(
              "relative rounded-xl border-2 border-dashed p-6 text-center transition-all cursor-pointer",
              dragActive ? "border-primary bg-primary/10" : "border-border hover:border-primary/50 hover:bg-muted/30",
              uploading ? "opacity-60 pointer-events-none" : ""
            )}
          >
            <input
              id="screenplay-file-upload"
              type="file"
              accept=".docx,.txt,.fountain,.md"
              className="sr-only"
              onChange={handleFileInputChange}
              disabled={uploading}
            />
            <label
              htmlFor="screenplay-file-upload"
              className="flex flex-col items-center justify-center gap-2 cursor-pointer"
            >
              <div className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary shadow-inner">
                <FileUp className="size-6" />
              </div>
              <div>
                <span className="text-sm font-semibold text-primary hover:underline">
                  {uploading ? "Extracting & Parsing Script…" : "Choose Script Document (.docx, .txt, .fountain, .md)"}
                </span>
                <span className="text-xs text-muted-foreground block sm:inline"> or drag &amp; drop file here</span>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Full native parsing for Word Document (.docx), Plain Text (.txt), Fountain (.fountain), and Markdown (.md)
              </p>
              {fileName && (
                <span className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-3 py-1 font-mono text-xs font-semibold text-emerald-400">
                  ✓ File loaded: {fileName}
                </span>
              )}
            </label>
          </div>

          {/* Script Textarea & Sample Action */}
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-medium text-foreground">Or paste &amp; review screenplay text:</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1.5 text-xs text-primary border-primary/30 hover:bg-primary/10"
                onClick={handleLoadSample}
              >
                <Sparkles className="size-3.5" />
                Load Chota Tenali Ep 1 (22 Scenes)
              </Button>
            </div>

            <Textarea
              rows={7}
              className="font-mono text-xs leading-relaxed"
              placeholder="01 | EXT. VILLAGE / MARKET — MORNING | 01:15&#10;AERIAL WIDE — सूरज की पहली किरणें...&#10;RAMA: मदद करेगा?&#10;PACHCHI: हाल सुनाऊँगा!..."
              value={scriptText}
              onChange={(e) => {
                setScriptText(e.target.value)
                parseAction(e.target.value)
              }}
            />
          </div>

          {/* Breakdown Summary Preview */}
          {parsing ? (
            <div className="py-4 text-center text-xs text-muted-foreground">Parsing screenplay…</div>
          ) : parsed.length > 0 ? (
            <div className="rounded-lg border bg-card/60 p-3 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2">
                  <Badge tone="green" dot>{parsed.length} Scenes detected</Badge>
                  <span className="font-mono font-medium text-foreground">
                    Total: {formatDuration(totalDuration)} ({Math.round(totalDuration / 60)} mins)
                  </span>
                </div>
                <div className="text-[11px] text-muted-foreground">
                  {allCharacters.length} Characters: {allCharacters.slice(0, 5).join(", ")}{allCharacters.length > 5 ? "…" : ""}
                </div>
              </div>

              <div className="max-h-48 overflow-y-auto rounded border bg-background/50 divide-y text-xs">
                {parsed.map((s) => (
                  <div key={s.scene_number} className="flex items-center justify-between px-3 py-1.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-primary">SC{String(s.scene_number).padStart(2, "0")}</span>
                      <span className="font-medium text-foreground">{s.title || "Untitled"}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      {s.characters.length > 0 && (
                        <span className="text-[10px] text-muted-foreground">{s.characters.slice(0, 3).join(", ")}</span>
                      )}
                      <span className="font-mono text-muted-foreground">{formatDuration(s.duration_sec)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : scriptText.trim() ? (
            <div className="rounded border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300">
              No scenes matched header format (e.g. `01 | EXT. LOCATION — TIME | 01:15` or `SCENE 1: TITLE`).
            </div>
          ) : null}

          <div className="flex items-center gap-2 pt-1">
            <Checkbox
              id="rep-scenes"
              checked={replaceExisting}
              onCheckedChange={(c) => setReplaceExisting(!!c)}
            />
            <label htmlFor="rep-scenes" className="text-xs text-foreground cursor-pointer">
              Replace existing scenes in this episode (safely preserves assignment histories and Google Drive links)
            </label>
          </div>
        </div>

        <DialogFooter className="pt-3 border-t">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            disabled={parsed.length === 0 || uploading || (!episode && !activeProjectId)}
            loading={importAction.isPending}
            onClick={() => importAction.mutate(undefined)}
          >
            Import {parsed.length > 0 ? `${parsed.length} Scenes` : "Screenplay"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ScreenplayReaderModal({
  episode, scene, canManage, onClose, onEdit
}: {
  episode: Episode
  scene: Scene
  canManage?: boolean
  onClose: () => void
  onEdit: () => void
}) {
  const driveLink = scene.reference_links?.find((l) =>
    l.url?.includes("drive.google.com") || l.label?.toLowerCase().includes("drive")
  )?.url || scene.reference_links?.[0]?.url

  // Parse lines for rich script formatting:
  // Detect [AI / CONTINUITY] or Camera/Audio cues, Dialogues vs Action
  const lines = (scene.description || "").split("\n")

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col">
        <DialogHeader className="border-b pb-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-bold text-primary">EP{String(episode.episode_number).padStart(2, "0")}</span>
              <span className="font-mono text-sm font-bold text-foreground">{scene.label}</span>
              <WorkStatusBadge status={scene.status} />
              {scene.duration_sec != null && (
                <span className="inline-flex items-center gap-1 rounded bg-primary/10 px-2 py-0.5 font-mono text-xs font-semibold text-primary">
                  <Clock className="size-3" />
                  {formatDuration(scene.duration_sec)} ({scene.duration_sec}s)
                </span>
              )}
            </div>
            {driveLink && (
              <a
                href={driveLink}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1 text-xs font-semibold text-white shadow hover:bg-blue-500"
              >
                <FolderOpen className="size-3.5" />
                Open in Google Drive ↗
              </a>
            )}
          </div>
          <DialogTitle className="mt-1 text-lg font-semibold">{scene.title || "Untitled Scene"}</DialogTitle>
          {scene.characters && scene.characters.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Cast:</span>
              {scene.characters.map((c) => (
                <span key={c} className="rounded bg-muted px-2 py-0.5 font-mono text-xs text-foreground font-medium">
                  {c}
                </span>
              ))}
            </div>
          )}
        </DialogHeader>

        <div className="flex-1 overflow-y-auto py-4 space-y-3 font-sans text-sm leading-relaxed">
          {lines.length === 0 || !scene.description?.trim() ? (
            <p className="text-center py-8 text-muted-foreground text-sm">No screenplay text recorded for this scene.</p>
          ) : (
            lines.map((rawLine, idx) => {
              const line = rawLine.trim()
              if (!line) return <div key={idx} className="h-2" />

              // Check for [AI / CONTINUITY] note
              if (line.startsWith("[AI / CONTINUITY]") || line.includes("[AI / CONTINUITY]")) {
                return (
                  <div key={idx} className="my-2 rounded-lg border border-purple-500/40 bg-purple-500/10 p-3 text-xs text-purple-200">
                    <span className="font-semibold text-purple-400 block mb-1">⚡ AI &amp; Continuity Execution Note:</span>
                    {line}
                  </div>
                )
              }

              // Check for dialogue speaker (e.g. "RAMA", "RAMA (O.S.)", "PACHCHI")
              const speakerMatch = line.match(/^([A-Z\s]{2,20}(?:\([^)]+\))?)\s*[:—\-]?\s*(.*)$/)
              if (speakerMatch && speakerMatch[1].length < 25 && !speakerMatch[1].includes("EXT.") && !speakerMatch[1].includes("INT.")) {
                return (
                  <div key={idx} className="my-2 pl-4 border-l-2 border-primary/50">
                    <div className="font-mono text-xs font-bold text-primary tracking-wide">
                      {speakerMatch[1]}
                    </div>
                    {speakerMatch[2] ? (
                      <p className="text-sm font-medium text-foreground mt-0.5">{speakerMatch[2]}</p>
                    ) : null}
                  </div>
                )
              }

              // Camera or action direction
              return (
                <p key={idx} className="text-foreground/90">
                  {line}
                </p>
              )
            })
          )}
        </div>

        <DialogFooter className="border-t pt-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {driveLink ? (
              <span className="text-[11px] text-muted-foreground truncate max-w-xs">
                Drive: <span className="font-mono">{driveLink}</span>
              </span>
            ) : (
              <span className="text-[11px] text-muted-foreground">No Google Drive link attached yet.</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {canManage && (
              <Button variant="outline" size="sm" onClick={onEdit}>
                <Pencil className="size-3.5" />Edit Scene &amp; Drive Link
              </Button>
            )}
            <Button size="sm" onClick={onClose}>Close</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
