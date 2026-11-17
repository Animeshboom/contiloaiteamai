import { CheckCircle2, Clock, Download, ExternalLink, History, Paperclip, XCircle } from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { api, errorMessage } from "@/lib/api"
import { formatDateTime } from "@/lib/format"
import type { SceneState, Submission, SubmissionStatus } from "@/lib/types"
import { cn } from "@/lib/utils"

const SUB_LABEL: Record<SubmissionStatus, string> = { pending_review: "Awaiting review", approved: "Approved", rejected: "Revision required" }
const SUB_TONE = { pending_review: "amber", approved: "green", rejected: "red" } as const

export function SubmissionStatusBadge({ status }: { status: SubmissionStatus }) {
  return <Badge tone={SUB_TONE[status]} dot>{SUB_LABEL[status]}</Badge>
}

const SCENE_LABEL: Record<SceneState | "none", string> = { none: "Not submitted", submitted: "In review", approved: "Approved", rejected: "Revise" }
const SCENE_STYLE: Record<SceneState | "none", string> = {
  none: "border-border text-muted-foreground",
  submitted: "border-primary/40 bg-primary/10 text-primary",
  approved: "border-success/40 bg-success/10 text-success",
  rejected: "border-destructive/40 bg-destructive/10 text-destructive",
}
const SCENE_ICON = { none: null, submitted: <Clock />, approved: <CheckCircle2 />, rejected: <XCircle /> }

/** A scene chip that carries its review state with icon + text (never colour alone). */
export function SceneStateChip({ label, state }: { label: string; state?: SceneState }) {
  const s = state ?? "none"
  return (
    <span className={cn("inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[11px] [&_svg]:size-3", SCENE_STYLE[s])}
      title={`${label}: ${SCENE_LABEL[s]}`}>
      {SCENE_ICON[s]}{label}<span className="sr-only"> — {SCENE_LABEL[s]}</span>
    </span>
  )
}

export function SceneStateLegend() {
  return (
    <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
      {(["none", "submitted", "approved", "rejected"] as const).map((s) => (
        <span key={s} className="inline-flex items-center gap-1.5"><span className={cn("size-2.5 rounded-sm border", SCENE_STYLE[s])} />{SCENE_LABEL[s]}</span>
      ))}
    </div>
  )
}

function fileSize(n: number) {
  return n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{title}</div>
      {children}
    </div>
  )
}

/** Full read-only view of one submission and its review history. */
export function SubmissionBody({ sub, showArtist = true, onOpenSubmission }: {
  sub: Submission; showArtist?: boolean; onOpenSubmission?: (id: number) => void
}) {
  async function download(attId: number, name: string) {
    try {
      await api.download(`/submissions/${sub.id}/attachments/${attId}`, name)
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <SubmissionStatusBadge status={sub.status} />
        <span className="font-mono">Rev {sub.revision_number}</span>
        {showArtist && <span>· {sub.artist_name}</span>}
        <span>· Submitted {formatDateTime(sub.submitted_at)}</span>
        {sub.is_late && <Badge tone="red">Late</Badge>}
        {sub.previous_submission_id && (
          onOpenSubmission
            ? <button type="button" className="inline-flex items-center gap-1 text-primary hover:underline cursor-pointer" onClick={() => onOpenSubmission(sub.previous_submission_id!)}>
                <History className="size-3" />Revision of #{sub.previous_submission_id}
              </button>
            : <span className="inline-flex items-center gap-1"><History className="size-3" />Revision of #{sub.previous_submission_id}</span>
        )}
      </div>

      <Section title={`Deliverables (${sub.deliverables.length})`}>
        <div className="flex flex-wrap gap-1.5">
          {sub.deliverables.map((d) => <SceneStateChip key={d.id} label={d.label} state={d.status} />)}
        </div>
        <p className="mt-1.5 text-[11px] text-muted-foreground">Artist reported {sub.scenes_completed_count} scene{sub.scenes_completed_count === 1 ? "" : "s"} completed.</p>
      </Section>

      <Section title="Work description"><p className="whitespace-pre-wrap text-sm">{sub.work_description}</p></Section>
      {sub.comments && <Section title="Artist comments"><p className="whitespace-pre-wrap text-sm text-muted-foreground">{sub.comments}</p></Section>}

      {sub.output_links.length > 0 && (
        <Section title="Output links">
          <ul className="space-y-1">
            {sub.output_links.map((l) => (
              <li key={l}>
                <a href={l} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex max-w-full items-center gap-1.5 break-all text-sm text-info hover:underline">
                  <ExternalLink className="size-3.5 shrink-0" />{l}
                </a>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {sub.attachments.length > 0 && (
        <Section title="Attachments">
          <ul className="divide-y rounded-md border">
            {sub.attachments.map((f) => (
              <li key={f.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                <Paperclip className="size-4 text-muted-foreground" />
                <span className="truncate">{f.original_filename}</span>
                <span className="text-xs text-muted-foreground">{fileSize(f.size_bytes)}</span>
                <Button variant="ghost" size="sm" className="ml-auto" onClick={() => download(f.id, f.original_filename)}><Download />Download</Button>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Review history">
        {sub.reviews.length === 0 ? <p className="text-sm text-muted-foreground">Not reviewed yet.</p> : (
          <ol className="space-y-2">
            {sub.reviews.map((r) => (
              <li key={r.id} className={cn("rounded-md border-l-2 bg-background/40 px-3 py-2", r.decision === "approved" ? "border-success" : "border-destructive")}>
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {r.decision === "approved"
                    ? <span className="inline-flex items-center gap-1 text-success"><CheckCircle2 className="size-3.5" />Approved</span>
                    : <span className="inline-flex items-center gap-1 text-destructive"><XCircle className="size-3.5" />Revision requested</span>}
                  <span className="text-muted-foreground">by {r.reviewer_name} · {formatDateTime(r.created_at)}</span>
                </div>
                {r.decision === "rejected" && r.approved_scene_ids.length > 0 && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Approved: {sub.deliverables.filter((d) => d.scene_id && r.approved_scene_ids.includes(d.scene_id)).map((d) => d.label).join(", ")}
                  </p>
                )}
                {r.feedback && <p className="mt-1 whitespace-pre-wrap text-sm">{r.feedback}</p>}
              </li>
            ))}
          </ol>
        )}
      </Section>
    </div>
  )
}
