import { useState, type FormEvent } from "react"
import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { KeyRound, Mail, Plus, ShieldCheck } from "lucide-react"

import { AISettingsCard } from "@/components/ai-settings"
import { BackupCard } from "@/components/backup-download"
import { ChangePasswordDialog } from "@/components/change-password"
import { EmailLogCard } from "@/components/email-log"
import { EmptyState, LoadingRows, PageHeader } from "@/components/common"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, Input } from "@/components/ui/form-controls"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { titleCase } from "@/lib/format"
import { supabaseHasAal2 } from "@/lib/mfa"
import { useAction, useRecipients } from "@/lib/queries"
import { usesSupabase } from "@/lib/supabase"
import type { Recipient } from "@/lib/types"

export default function SettingsPage() {
  const { user, config } = useAuth()
  const isAdmin = user?.role === "admin"
  const [pwOpen, setPwOpen] = useState(false)

  return (
    <>
      <PageHeader title="Settings" description={isAdmin ? "Studio configuration and report recipients." : "Your account and studio configuration."} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6">
          <Card>
            <CardHeader><CardTitle>Account</CardTitle><CardDescription>{user?.email}</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              <Button variant="outline" onClick={() => setPwOpen(true)}><KeyRound />Change password</Button>
              {isAdmin && <TwoStepStatus mfaEnabled={Boolean(user?.mfa_enabled)} />}
            </CardContent>
          </Card>
          {(isAdmin || user?.role === "team_lead") && <BackupCard />}
          <Card>
            <CardHeader><CardTitle>Studio</CardTitle><CardDescription>Set via environment configuration</CardDescription></CardHeader>
            <CardContent className="grid gap-3 text-sm">
              <Row k="Timezone" v={config?.studio_timezone} />
              <Row k="Default EOD deadline" v={config ? `${String(config.eod_deadline_hour).padStart(2, "0")}:00` : undefined} />
              <Row k="Email delivery" v={config ? (config.email_provider === "mcp" ? "Gmail MCP server" : "In-process (development)") : undefined} />
              <Row k="Gmail backend" v={config ? (config.gmail_backend === "gmail" ? "Gmail API (OAuth)" : "Mock — writes .eml files") : undefined} />
              <Row k="AI provider" v={config ? (config.ai_enabled ? `${config.ai_provider} · ${config.ai_model}` : "Not configured (template / basic parser fallback)") : undefined} />
            </CardContent>
          </Card>
        </div>
        <div className="space-y-6 lg:col-span-2">
          {isAdmin && <AISettingsCard />}
          <RecipientsCard editable={isAdmin} />
          {isAdmin && <EmailLogCard />}
        </div>
      </div>
      <ChangePasswordDialog open={pwOpen} onOpenChange={setPwOpen} />
    </>
  )
}

function TwoStepStatus({ mfaEnabled }: { mfaEnabled: boolean }) {
  // With Supabase Auth the factor lives in Supabase: "on" means this session was verified with a code (aal2).
  const supa = useQuery({ queryKey: ["mfa-aal"], queryFn: supabaseHasAal2, enabled: usesSupabase, staleTime: 60_000 })
  const on = usesSupabase ? supa.data === true : mfaEnabled
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-4 text-sm">
      <span className="flex items-center gap-2"><ShieldCheck className="size-4 text-muted-foreground" />
        Two-step login: {on ? <Badge tone="green" dot>On</Badge> : <Badge tone="yellow">Off</Badge>}
      </span>
      {!on && <Button asChild size="sm"><Link to="/admin/two-step">Set up two-step login</Link></Button>}
    </div>
  )
}

function Row({ k, v }: { k: string; v?: string }) {
  return <div className="flex justify-between gap-4"><span className="text-muted-foreground">{k}</span><span className="text-right">{v ?? "—"}</span></div>
}

function RecipientsCard({ editable }: { editable: boolean }) {
  const { data, isLoading } = useRecipients()
  const [email, setEmail] = useState("")
  const [name, setName] = useState("")
  const add = useAction(() => api.post<Recipient>("/recipients", { email, name }), {
    success: "Recipient authorized", invalidate: [["recipients"]], onSuccess: () => { setEmail(""); setName("") },
  })
  const toggle = useAction((r: Recipient) => api.patch<Recipient>(`/recipients/${r.id}`, { is_active: !r.is_active }), {
    success: (r) => `${r.email} ${r.is_active ? "enabled" : "disabled"}`, invalidate: [["recipients"]],
  })
  const submit = (e: FormEvent) => { e.preventDefault(); add.mutate(undefined) }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Mail className="size-4" />Authorized report recipients</CardTitle>
        <CardDescription>
          End-of-day reports can only be sent to these addresses. The email integration rejects anyone else, including recipients an AI draft suggests.
          {!editable && " Only admins can change this list."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {editable && (
          <form onSubmit={submit} className="grid gap-3 rounded-md border bg-background/40 p-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <Field label="Name" htmlFor="r-name"><Input id="r-name" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} placeholder="Head of Production" /></Field>
            <Field label="Email" htmlFor="r-email"><Input id="r-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
            <Button type="submit" loading={add.isPending}><Plus />Add</Button>
          </form>
        )}
        {isLoading ? <LoadingRows rows={2} /> : !data?.length ? <EmptyState title="No recipients configured" /> : (
          <Table>
            <TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Email</TableHead><TableHead>Purpose</TableHead><TableHead>Status</TableHead>{editable && <TableHead />}</TableRow></TableHeader>
            <TableBody>
              {data.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-medium">{r.name}</TableCell>
                  <TableCell className="font-mono text-xs">{r.email}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{r.purpose === "eod_report" ? "EOD report" : titleCase(r.purpose)}</TableCell>
                  <TableCell>{r.is_active ? <Badge tone="green" dot>Active</Badge> : <Badge>Disabled</Badge>}</TableCell>
                  {editable && (
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" onClick={() => toggle.mutate(r)} disabled={toggle.isPending}>{r.is_active ? "Disable" : "Enable"}</Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
