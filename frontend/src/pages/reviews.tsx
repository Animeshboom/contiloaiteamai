import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { CheckCircle2, Inbox, RotateCcw } from "lucide-react"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common"
import { SubmissionBody } from "@/components/submission-view"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Checkbox, Field, Textarea } from "@/components/ui/form-controls"
import { api } from "@/lib/api"
import { formatDateTime } from "@/lib/format"
import { WORK_KEYS, useAction, useSubmissions } from "@/lib/queries"
import type { Submission } from "@/lib/types"
import { cn } from "@/lib/utils"

export default function ReviewsPage() {
  const [params, setParams] = useSearchParams()
  const { data, isLoading, error, refetch } = useSubmissions({ status: "pending_review" })
  const queue = data ?? []
  const selectedId = Number(params.get("open")) || queue[0]?.id
  const selected = queue.find((s) => s.id === selectedId) ?? queue[0]

  return (
    <>
      <PageHeader title="Reviews" description="Pending submissions, oldest first. Approve scenes or request a revision with feedback." />
      {error ? <ErrorState error={error} onRetry={refetch} /> : isLoading ? <LoadingRows /> : queue.length === 0 ? (
        <EmptyState icon={<Inbox />} title="Review queue is empty" description="New submissions from your artists will appear here." />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[20rem_1fr]">
          <Card className="h-fit p-1">
            <div className="px-3 py-2 text-xs text-muted-foreground">{queue.length} awaiting review</div>
            <ul className="space-y-0.5">
              {queue.map((s) => (
                <li key={s.id}>
                  <button type="button" onClick={() => setParams({ open: String(s.id) }, { replace: true })}
                    className={cn("w-full rounded-md px-3 py-2.5 text-left transition-colors hover:bg-accent cursor-pointer",
                      s.id === selected?.id && "bg-accent ring-1 ring-primary/40")}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{s.artist_name.replace(/ \(.*\)/, "")}</span>
                      {s.is_resubmission && <Badge tone="blue">Rev {s.revision_number}</Badge>}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">{s.project_code} · {s.assignment_title}</div>
                    <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
                      <span>{formatDateTime(s.submitted_at)}</span>
                      <span>· {s.deliverables.length} item{s.deliverables.length === 1 ? "" : "s"}</span>
                      {s.is_late && <span className="text-destructive">· late</span>}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          {selected && <ReviewPanel key={selected.id} sub={selected} onDone={() => setParams({}, { replace: true })} />}
        </div>
      )}
    </>
  )
}

function ReviewPanel({ sub, onDone }: { sub: Submission; onDone: () => void }) {
  const sceneDeliverables = sub.deliverables.filter((d) => d.scene_id !== null)
  const [approved, setApproved] = useState<number[]>(sceneDeliverables.map((d) => d.scene_id!))
  const [feedback, setFeedback] = useState("")
  useEffect(() => setApproved(sceneDeliverables.map((d) => d.scene_id!)), [sub.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const partial = sceneDeliverables.length > 0 && approved.length < sceneDeliverables.length
  const needsFeedback = partial && feedback.trim().length < 3

  const approve = useAction(
    () => api.post<Submission>(`/submissions/${sub.id}/review`, {
      decision: "approved", feedback: feedback.trim() || null,
      approved_scene_ids: sceneDeliverables.length ? approved : null,
    }),
    { success: (r) => (r.status === "approved" ? "Approved — the artist can see it now" : "Partially approved; revision requested for the rest"),
      invalidate: WORK_KEYS, onSuccess: onDone },
  )
  const reject = useAction(
    () => api.post<Submission>(`/submissions/${sub.id}/review`, { decision: "rejected", feedback: feedback.trim() }),
    { success: "Revision requested", invalidate: WORK_KEYS, onSuccess: onDone },
  )

  return (
    <Card className="p-5">
      <div className="mb-4">
        <div className="font-mono text-[11px] text-muted-foreground">
          Submission #{sub.id} · {sub.project_code}{sub.episode_number != null && ` · EP${String(sub.episode_number).padStart(2, "0")} ${sub.episode_title}`}
        </div>
        <h2 className="text-base font-semibold">{sub.assignment_title}</h2>
        <div className="text-xs text-muted-foreground">Due {formatDateTime(sub.deadline)}</div>
      </div>
      <SubmissionBody sub={sub} />

      <div className="mt-6 space-y-4 rounded-lg border border-primary/25 bg-primary/5 p-4">
        <div className="text-sm font-semibold">Your decision</div>
        {sceneDeliverables.length > 1 && (
          <Field label="Approve these scenes (unchecked scenes will be sent back for revision)">
            <div className="flex flex-wrap gap-3">
              {sceneDeliverables.map((d) => (
                <label key={d.id} className="flex items-center gap-2 text-sm cursor-pointer">
                  <Checkbox checked={approved.includes(d.scene_id!)}
                    onCheckedChange={(c) => setApproved(c ? [...approved, d.scene_id!] : approved.filter((x) => x !== d.scene_id))} />
                  <span className="font-mono">{d.label}</span>
                </label>
              ))}
            </div>
          </Field>
        )}
        <Field label="Feedback for the artist" htmlFor="rv-fb" hint="Required when requesting a revision."
          error={needsFeedback ? "Explain what needs revising for the unchecked scenes" : undefined}>
          <Textarea id="rv-fb" rows={3} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="e.g. Great motion in SC01. SC02: rain particles flicker at 00:04 — re-render with a fixed seed." />
        </Field>
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="outline" className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
            disabled={feedback.trim().length < 3 || approve.isPending} loading={reject.isPending} onClick={() => reject.mutate(undefined)}>
            <RotateCcw />Request revision
          </Button>
          <Button disabled={(sceneDeliverables.length > 0 && approved.length === 0) || needsFeedback || reject.isPending}
            loading={approve.isPending} onClick={() => approve.mutate(undefined)}>
            <CheckCircle2 />{partial ? `Approve ${approved.length} of ${sceneDeliverables.length}` : "Approve"}
          </Button>
        </div>
      </div>
    </Card>
  )
}
