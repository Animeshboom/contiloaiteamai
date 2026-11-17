import { useEffect, useMemo, useState, type FormEvent } from "react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { FileUp, Link2, Plus, Send, X } from "lucide-react"
import { toast } from "sonner"

import { EmptyState, LoadingRows, PageHeader } from "@/components/common"
import { SceneStateChip, SceneStateLegend } from "@/components/submission-view"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, Input, NativeSelect, Textarea } from "@/components/ui/form-controls"
import { api, errorMessage } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { formatDateTime, relativeDeadline } from "@/lib/format"
import { WORK_KEYS, useAssignments, useSubmissions } from "@/lib/queries"
import type { Assignment, Submission } from "@/lib/types"
import { cn } from "@/lib/utils"

const ALLOWED = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".webm", ".pdf", ".txt", ".zip", ".json", ".wav", ".mp3"]
const OPEN = ["assigned", "in_progress", "submitted", "revision_required"]

export default function SubmitWorkPage() {
  const { user, config } = useAuth()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const assignments = useAssignments()

  const open = useMemo(() => (assignments.data ?? []).filter((a) => {
    const me = a.assignees.find((x) => x.user_id === user?.id)
    return me && OPEN.includes(me.status)
  }), [assignments.data, user?.id])

  const selectedId = Number(params.get("assignment")) || undefined
  const assignment = open.find((a) => a.id === selectedId)
  const me = assignment?.assignees.find((x) => x.user_id === user?.id)
  const history = useSubmissions({ assignment_id: selectedId }, !!selectedId)

  const [sceneIds, setSceneIds] = useState<number[]>([])
  const [description, setDescription] = useState("")
  const [links, setLinks] = useState<string[]>([""])
  const [comments, setComments] = useState("")
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)

  const submittable = (sid: number) => {
    const st = me?.scene_states[String(sid)]
    return st !== "submitted" && st !== "approved"
  }

  // Preselect scenes that need revision (or everything still open) when an assignment is chosen.
  useEffect(() => {
    if (!assignment || !me) return
    const rejected = assignment.scenes.filter((s) => me.scene_states[String(s.id)] === "rejected").map((s) => s.id)
    setSceneIds(rejected)
  }, [assignment?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const lastFeedback = useMemo(() => {
    const rejected = (history.data ?? []).find((s) => s.status === "rejected")
    return rejected?.reviews.at(-1)?.feedback ?? null
  }, [history.data])

  const pendingDeliverableOnly = assignment && assignment.scenes.length === 0 && me?.status === "submitted"
  const remaining = assignment?.scenes.filter((s) => submittable(s.id)) ?? []
  const fileErrors = files.map((f) => {
    const ext = "." + (f.name.split(".").pop() ?? "").toLowerCase()
    if (!ALLOWED.includes(ext)) return `${f.name}: ${ext} files are not allowed`
    if (config && f.size > config.max_upload_mb * 1024 * 1024) return `${f.name}: larger than ${config.max_upload_mb} MB`
    return null
  }).filter(Boolean) as string[]
  const cleanLinks = links.map((l) => l.trim()).filter(Boolean)
  const badLink = cleanLinks.find((l) => !/^https?:\/\/\S+$/i.test(l))
  const canSubmit = !!assignment && description.trim().length >= 3 && !badLink && fileErrors.length === 0 &&
    (assignment.scenes.length === 0 ? !pendingDeliverableOnly : sceneIds.length > 0)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!assignment) return
    setBusy(true)
    let sub: Submission
    try {
      sub = await api.post<Submission>("/submissions", {
        assignment_id: assignment.id, scene_ids: sceneIds, work_description: description,
        output_links: cleanLinks, comments: comments || null,
      })
    } catch (err) {
      toast.error(errorMessage(err))
      setBusy(false)
      return
    }
    const failed: string[] = []
    for (const f of files) {
      try {
        await api.upload(`/submissions/${sub.id}/attachments`, f)
      } catch (err) {
        failed.push(`${f.name} (${errorMessage(err)})`)
      }
    }
    WORK_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: k }))
    setBusy(false)
    if (failed.length) toast.warning(`Submitted #${sub.id}, but some files failed: ${failed.join("; ")}`, { duration: 10000 })
    else toast.success(`Submission #${sub.id} sent for review`)
    navigate(`/artist/history?open=${sub.id}`)
  }

  return (
    <>
      <PageHeader title="Submit work" description="Submit the scenes you've finished. You can submit some scenes now and the rest later. Your lead reviews each one." />
      {assignments.isLoading ? <LoadingRows /> : open.length === 0 ? (
        <EmptyState title="Nothing to submit" description="You have no open assignments right now."
          action={<Button asChild size="sm" variant="outline"><Link to="/artist/assignments">View my assignments</Link></Button>} />
      ) : (
        <form onSubmit={submit} className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <Card>
              <CardHeader><CardTitle>1 · Assignment &amp; scenes</CardTitle></CardHeader>
              <CardContent className="grid gap-4">
                <Field label="Assignment" htmlFor="sw-a">
                  <NativeSelect id="sw-a" value={selectedId ?? ""} onChange={(e) => setParams(e.target.value ? { assignment: e.target.value } : {})}>
                    <option value="">Select an assignment…</option>
                    {open.map((a) => <option key={a.id} value={a.id}>{a.project_code} · {a.title}</option>)}
                  </NativeSelect>
                </Field>
                {assignment && <AssignmentContext a={assignment} />}
                {assignment && assignment.scenes.length > 0 && me && (
                  <Field label={`Completed scenes to submit (${sceneIds.length} selected)`}>
                    <div className="rounded-md border p-3">
                      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                        {assignment.scenes.map((s) => {
                          const st = me.scene_states[String(s.id)] as "submitted" | "approved" | "rejected" | undefined
                          const can = submittable(s.id)
                          const on = sceneIds.includes(s.id)
                          return (
                            <button key={s.id} type="button" disabled={!can} aria-pressed={on}
                              onClick={() => setSceneIds(on ? sceneIds.filter((x) => x !== s.id) : [...sceneIds, s.id])}
                              className={cn("flex flex-col items-start gap-1 rounded-md border p-2 text-left transition-colors",
                                can ? "cursor-pointer hover:bg-accent" : "cursor-not-allowed opacity-60",
                                on && "border-primary bg-primary/10")}>
                              <span className="font-mono text-xs">EP{String(s.episode_number).padStart(2, "0")} {s.label}</span>
                              <SceneStateChip label={st === "rejected" ? "needs revision" : st === "submitted" ? "in review" : st === "approved" ? "approved" : "open"} state={st} />
                            </button>
                          )
                        })}
                      </div>
                      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                        <SceneStateLegend />
                        {remaining.length > 1 && <Button type="button" variant="ghost" size="sm" onClick={() => setSceneIds(remaining.map((s) => s.id))}>Select all open</Button>}
                      </div>
                    </div>
                  </Field>
                )}
                {pendingDeliverableOnly && <p className="text-sm text-warning">Your previous submission for this deliverable is still awaiting review.</p>}
                {lastFeedback && me?.status === "revision_required" && (
                  <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm">
                    <div className="text-[11px] font-medium uppercase tracking-wider text-destructive">Latest feedback from your lead</div>
                    <p className="mt-1 whitespace-pre-wrap">{lastFeedback}</p>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>2 · What you delivered</CardTitle></CardHeader>
              <CardContent className="grid gap-4">
                <Field label="Work description" htmlFor="sw-desc" hint="What you did, tools/models used, anything the reviewer should check.">
                  <Textarea id="sw-desc" required minLength={3} rows={4} value={description} onChange={(e) => setDescription(e.target.value)} />
                </Field>
                <Field label="Output / reference links" error={badLink ? `Not a valid http(s) link: ${badLink}` : undefined}>
                  <div className="space-y-2">
                    {links.map((l, i) => (
                      <div key={i} className="flex gap-2">
                        <div className="relative flex-1">
                          <Link2 className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
                          <Input className="pl-8" type="url" placeholder="https://drive.google.com/…" value={l} aria-label={`Link ${i + 1}`}
                            onChange={(e) => setLinks(links.map((x, j) => (j === i ? e.target.value : x)))} />
                        </div>
                        {links.length > 1 && <Button type="button" variant="ghost" size="icon" onClick={() => setLinks(links.filter((_, j) => j !== i))} aria-label="Remove link"><X /></Button>}
                      </div>
                    ))}
                    {links.length < 20 && <Button type="button" variant="ghost" size="sm" onClick={() => setLinks([...links, ""])}><Plus />Add link</Button>}
                  </div>
                </Field>
                <Field label="Attachments (optional)" hint={`${ALLOWED.join(" ")} · up to ${config?.max_upload_mb ?? 25} MB each · max 10`}>
                  <label className="flex cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed px-4 py-5 text-sm text-muted-foreground hover:bg-accent/40">
                    <FileUp className="size-4" />Choose files
                    <input type="file" multiple className="sr-only" accept={ALLOWED.join(",")}
                      onChange={(e) => { setFiles([...files, ...Array.from(e.target.files ?? [])].slice(0, 10)); e.target.value = "" }} />
                  </label>
                  {files.length > 0 && (
                    <ul className="mt-2 space-y-1 text-sm">
                      {files.map((f, i) => (
                        <li key={i} className="flex items-center gap-2">
                          <span className="truncate">{f.name}</span>
                          <span className="text-xs text-muted-foreground">{(f.size / 1024 / 1024).toFixed(1)} MB</span>
                          <Button type="button" variant="ghost" size="icon" className="ml-auto size-7" onClick={() => setFiles(files.filter((_, j) => j !== i))} aria-label={`Remove ${f.name}`}><X /></Button>
                        </li>
                      ))}
                    </ul>
                  )}
                  {fileErrors.map((m) => <p key={m} className="text-xs text-destructive">{m}</p>)}
                </Field>
                <Field label="Comments for the reviewer (optional)" htmlFor="sw-com">
                  <Textarea id="sw-com" rows={2} value={comments} onChange={(e) => setComments(e.target.value)} />
                </Field>
              </CardContent>
            </Card>
          </div>

          <div className="lg:sticky lg:top-20 lg:self-start">
            <Card>
              <CardHeader>
                <CardTitle>Summary</CardTitle>
                <CardDescription>Submitting does not mark work as complete — your lead approves or requests a revision.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">Scenes</span><span className="font-mono">{assignment?.scenes.length ? sceneIds.length : "—"}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Links</span><span className="font-mono">{cleanLinks.length}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Files</span><span className="font-mono">{files.length}</span></div>
                <Button type="submit" className="w-full" disabled={!canSubmit} loading={busy}><Send />Submit for review</Button>
              </CardContent>
            </Card>
          </div>
        </form>
      )}
    </>
  )
}

function AssignmentContext({ a }: { a: Assignment }) {
  const dl = relativeDeadline(a.deadline)
  return (
    <div className="rounded-md border bg-background/40 px-3 py-2 text-xs text-muted-foreground">
      <span className="text-foreground">{a.project_title}</span>
      {a.episode_number != null && <> · EP{String(a.episode_number).padStart(2, "0")} {a.episode_title}</>}
      {" · "}Due {formatDateTime(a.deadline)} <span className={cn(dl.overdue && "text-destructive")}>({dl.text})</span>
      {a.expected_deliverables && <div className="mt-1">Expected: {a.expected_deliverables}</div>}
    </div>
  )
}
