import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, ArrowLeft, Check, FileEdit, MailCheck, Save, Send, Undo2 } from "lucide-react"
import { toast } from "sonner"

import { ErrorState, LoadingRows } from "@/components/common"
import { ReportMetricsView } from "@/components/report-metrics"
import { AiStatusBadge, ReportStatusBadge } from "@/components/report-status"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ConfirmDialog } from "@/components/ui/dialog"
import { Checkbox, Field, Input, Textarea } from "@/components/ui/form-controls"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/misc"
import { api, errorMessage } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { formatDate, formatDateTime } from "@/lib/format"
import { useAction, useRecipients, useReport } from "@/lib/queries"
import type { Report } from "@/lib/types"
import { cn } from "@/lib/utils"

const STEPS = ["draft", "approved", "sent"] as const

function Steps({ status }: { status: Report["status"] }) {
  const idx = status === "failed" ? 1 : STEPS.indexOf(status as (typeof STEPS)[number])
  return (
    <ol className="flex items-center gap-2 text-xs">
      {["Draft & review", "Approved by lead", "Sent via Gmail"].map((label, i) => (
        <li key={label} className="flex items-center gap-2">
          <span className={cn("grid size-5 place-items-center rounded-full border font-mono text-[10px]",
            i < idx || status === "sent" ? "border-success bg-success/15 text-success" : i === idx ? "border-primary text-primary" : "text-muted-foreground")}>
            {i < idx || status === "sent" ? <Check className="size-3" /> : i + 1}
          </span>
          <span className={i <= idx ? "text-foreground" : "text-muted-foreground"}>{label}</span>
          {i < 2 && <span className="h-px w-6 bg-border" />}
        </li>
      ))}
    </ol>
  )
}

export default function ReportDetailPage() {
  const { id } = useParams()
  const { user, config } = useAuth()
  const qc = useQueryClient()
  const base = user?.role === "admin" ? "/admin/reports" : "/lead/reports"
  const { data: r, isLoading, error, refetch } = useReport(Number(id))
  const recipientsQ = useRecipients()
  const authorized = (recipientsQ.data ?? []).filter((x) => x.is_active)

  const [subject, setSubject] = useState("")
  const [body, setBody] = useState("")
  const [recipients, setRecipients] = useState<string[]>([])
  const [confirm, setConfirm] = useState(false)
  const [sending, setSending] = useState(false)
  useEffect(() => {
    if (r) { setSubject(r.subject); setBody(r.body); setRecipients(r.recipients) }
  }, [r?.id, r?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const invalidate = [["report"], ["reports"], ["email-logs"]]
  const save = useAction(() => api.patch<Report>(`/reports/${id}`, { subject, body, recipients }), { success: "Draft saved", invalidate })
  const draft = useAction(() => api.post<Report>(`/reports/${id}/gmail-draft`), { success: "Saved to Gmail drafts (not sent)", invalidate })
  const revoke = useAction(() => api.post<Report>(`/reports/${id}/revoke`), { success: "Returned to draft", invalidate })

  if (error) return <ErrorState error={error} onRetry={refetch} />
  if (isLoading || !r) return <LoadingRows />

  const isDraft = r.status === "draft"
  const dirty = isDraft && (subject !== r.subject || body !== r.body || [...recipients].sort().join() !== [...r.recipients].sort().join())

  /** Explicit two-step action by the lead: approve exactly this text + recipients, then send. */
  async function approveAndSend() {
    setSending(true)
    try {
      if (isDraft) {
        if (dirty) await api.patch(`/reports/${id}`, { subject, body, recipients })
        await api.post(`/reports/${id}/approve`, { recipients })
      }
      const res = await api.post<Report>(`/reports/${id}/send`)
      if (res.status === "sent") toast.success(`Report sent to ${res.recipients.length} recipient(s)`)
      else toast.error(`Delivery ${res.delivery_status}: ${res.email_error ?? "see details"}`)
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setSending(false)
      setConfirm(false)
      invalidate.forEach((k) => qc.invalidateQueries({ queryKey: k }))
    }
  }

  return (
    <>
      <Button variant="ghost" size="sm" asChild className="-ml-2 mb-3"><Link to={base}><ArrowLeft />All reports</Link></Button>
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">Report #{r.id}</span>
            <ReportStatusBadge status={r.status} />
            <AiStatusBadge status={r.ai_status} />
          </div>
          <h1 className="mt-1 text-xl font-semibold tracking-tight">{formatDate(r.report_date, true)}</h1>
          <p className="text-sm text-muted-foreground">Generated by {r.created_by_name} · {formatDateTime(r.created_at)} · {r.metrics.as_of}</p>
        </div>
        <Steps status={r.status} />
      </div>

      {r.ai_note && r.ai_status !== "template" && (
        <div className="mb-4 flex gap-2 rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" /><span>{r.ai_note}. The figures-only template was used instead.</span>
        </div>
      )}
      {r.status === "failed" && (
        <div className="mb-4 flex gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
          <span>Delivery {r.delivery_status}: {r.email_error ?? "unknown error"}. Retry, or return it to draft to change recipients.</span>
        </div>
      )}
      {r.status === "sent" && (
        <div className="mb-4 flex gap-2 rounded-md border border-success/30 bg-success/5 px-3 py-2 text-sm">
          <MailCheck className="mt-0.5 size-4 shrink-0 text-success" />
          <span>Sent {formatDateTime(r.sent_at)} by {r.sent_by_name} to {r.recipients.join(", ")} · approved by {r.approved_by_name}
            {r.gmail_message_id && <> · Gmail ref <span className="font-mono text-xs">{r.gmail_message_id}</span></>}</span>
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[1fr_26rem]">
        <Card>
          <CardHeader>
            <CardTitle>Email</CardTitle>
            <CardDescription>{isDraft ? "Edit freely. What you approve is exactly what is sent." : "Locked after approval. Return to draft to edit."}</CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue={isDraft ? "edit" : "preview"}>
              <TabsList>
                <TabsTrigger value="edit"><FileEdit className="mr-1 size-3.5" />Edit</TabsTrigger>
                <TabsTrigger value="preview">Preview</TabsTrigger>
              </TabsList>
              <TabsContent value="edit" className="grid gap-4">
                <Field label="Subject" htmlFor="rp-subj"><Input id="rp-subj" value={subject} disabled={!isDraft} onChange={(e) => setSubject(e.target.value)} /></Field>
                <Field label="Body (plain text)" htmlFor="rp-body">
                  <Textarea id="rp-body" value={body} disabled={!isDraft} onChange={(e) => setBody(e.target.value)} className="min-h-[34rem] font-mono text-xs leading-relaxed" />
                </Field>
              </TabsContent>
              <TabsContent value="preview">
                <div className="overflow-hidden rounded-md border bg-background/60">
                  <div className="space-y-1 border-b px-4 py-3 text-sm">
                    <div><span className="inline-block w-16 text-muted-foreground">To</span>{recipients.join(", ") || <span className="text-destructive">no recipients</span>}</div>
                    <div><span className="inline-block w-16 text-muted-foreground">Subject</span><span className="font-medium">{subject}</span></div>
                    <div><span className="inline-block w-16 text-muted-foreground">Via</span>{config?.email_provider === "mcp" ? "Gmail MCP server" : "In-process"} · {config?.gmail_backend === "gmail" ? "Gmail API" : "mock (.eml)"}</div>
                  </div>
                  <pre className="max-h-[40rem] overflow-auto whitespace-pre-wrap px-4 py-3 font-mono text-xs leading-relaxed">{body}</pre>
                </div>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Recipients</CardTitle>
              <CardDescription>Only authorized management addresses (configured by an admin) can receive reports.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {authorized.map((a) => (
                <label key={a.id} className="flex items-center gap-2 text-sm cursor-pointer">
                  <Checkbox disabled={!isDraft} checked={recipients.includes(a.email)}
                    onCheckedChange={(c) => setRecipients(c ? [...recipients, a.email] : recipients.filter((x) => x !== a.email))} />
                  <span>{a.name}</span><span className="ml-auto font-mono text-xs text-muted-foreground">{a.email}</span>
                </label>
              ))}
              {authorized.length === 0 && <p className="text-sm text-warning">No authorized recipients configured. Ask an admin to add them in Settings.</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Actions</CardTitle></CardHeader>
            <CardContent className="grid gap-2">
              {isDraft && (
                <>
                  <Button variant="outline" disabled={!dirty} loading={save.isPending} onClick={() => save.mutate(undefined)}><Save />Save draft</Button>
                  <Button variant="outline" loading={draft.isPending} disabled={dirty || recipients.length === 0} onClick={() => draft.mutate(undefined)}
                    title={dirty ? "Save first" : undefined}><MailCheck />Save to Gmail drafts</Button>
                  <Button disabled={recipients.length === 0 || body.trim().length < 10} onClick={() => setConfirm(true)}><Send />Approve &amp; send…</Button>
                </>
              )}
              {(r.status === "approved" || r.status === "failed") && (
                <>
                  <Button loading={sending} onClick={() => setConfirm(true)}><Send />{r.status === "failed" ? "Retry send" : "Send now"}</Button>
                  <Button variant="outline" loading={revoke.isPending} onClick={() => revoke.mutate(undefined)}><Undo2 />Return to draft</Button>
                </>
              )}
              {r.status === "sent" && <p className="text-sm text-muted-foreground">This report has been delivered and is kept in history.</p>}
              {r.gmail_draft_id && r.status !== "sent" && <p className="text-xs text-muted-foreground">Gmail draft saved ({r.gmail_draft_id}).</p>}
            </CardContent>
          </Card>

          <ReportMetricsView m={r.metrics} compact />
        </div>
      </div>

      <ConfirmDialog
        open={confirm} onOpenChange={setConfirm} loading={sending} confirmLabel={isDraft ? "Approve & send" : "Send"}
        title={isDraft ? "Approve and send this report?" : "Send this approved report?"}
        description={<>
          “{subject}” will be sent from the studio Gmail account to <strong>{recipients.join(", ")}</strong>.
          {isDraft && " You are approving exactly this text and recipient list."} This cannot be unsent.
        </>}
        onConfirm={approveAndSend}
      />
    </>
  )
}
