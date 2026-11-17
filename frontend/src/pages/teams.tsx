import { useState, type FormEvent } from "react"
import { Building2, Pencil, Plus, Trash2, Users } from "lucide-react"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ConfirmDialog, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Field, Input, NativeSelect, Textarea } from "@/components/ui/form-controls"
import { api } from "@/lib/api"
import { useAction, useTeams, useUsers } from "@/lib/queries"
import type { Team } from "@/lib/types"

export default function TeamsPage() {
  const { data, isLoading, error, refetch } = useTeams()
  const [dialog, setDialog] = useState<{ team?: Team } | null>(null)
  const [deleting, setDeleting] = useState<Team | null>(null)
  const del = useAction(() => api.del(`/teams/${deleting!.id}`), { success: "Team deleted", invalidate: [["teams"]], onSuccess: () => setDeleting(null) })

  return (
    <>
      <PageHeader title="Teams" description="Departments and units. Each team's lead manages its artists' assignments and attendance."
        actions={<Button onClick={() => setDialog({})}><Plus />New team</Button>} />
      {error ? <ErrorState error={error} onRetry={refetch} /> : isLoading ? <LoadingRows /> : !data?.length ? (
        <EmptyState icon={<Building2 />} title="No teams yet" action={<Button size="sm" onClick={() => setDialog({})}><Plus />New team</Button>} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((t) => (
            <Card key={t.id} className="p-5">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">{t.department ?? "No department"}</div>
                  <div className="mt-0.5 font-semibold">{t.name}</div>
                </div>
                <div className="flex">
                  <Button variant="ghost" size="icon" className="size-8" onClick={() => setDialog({ team: t })} aria-label={`Edit ${t.name}`}><Pencil /></Button>
                  <Button variant="ghost" size="icon" className="size-8 text-muted-foreground hover:text-destructive" onClick={() => setDeleting(t)} aria-label={`Delete ${t.name}`}><Trash2 /></Button>
                </div>
              </div>
              {t.description && <p className="mt-2 text-xs text-muted-foreground">{t.description}</p>}
              <div className="mt-4 flex items-center justify-between border-t pt-3 text-sm">
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Lead</div>
                  <div className={t.lead ? "" : "text-warning"}>{t.lead?.full_name ?? "Not assigned"}</div>
                </div>
                <div className="flex items-center gap-1.5 text-muted-foreground"><Users className="size-4" /><span className="font-mono tabular">{t.member_count}</span></div>
              </div>
            </Card>
          ))}
        </div>
      )}
      {dialog && <TeamDialog team={dialog.team} onClose={() => setDialog(null)} />}
      <ConfirmDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)} destructive loading={del.isPending} confirmLabel="Delete team"
        title={`Delete ${deleting?.name}?`} description="Only teams with no active members can be deleted. Move members to another team first."
        onConfirm={() => del.mutate(undefined)} />
    </>
  )
}

function TeamDialog({ team, onClose }: { team?: Team; onClose: () => void }) {
  const leads = useUsers({ role: "team_lead" })
  const [name, setName] = useState(team?.name ?? "")
  const [department, setDepartment] = useState(team?.department ?? "")
  const [description, setDescription] = useState(team?.description ?? "")
  const [leadId, setLeadId] = useState(team?.lead ? String(team.lead.id) : "")
  const body = { name, department: department || null, description: description || null }
  const save = useAction(
    () => team
      ? api.patch(`/teams/${team.id}`, { ...body, ...(leadId ? { lead_id: Number(leadId) } : { clear_lead: true }) })
      : api.post("/teams", { ...body, lead_id: leadId ? Number(leadId) : null }),
    { success: team ? "Team updated" : "Team created", invalidate: [["teams"], ["users"]], onSuccess: onClose },
  )
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(undefined) }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{team ? "Edit team" : "New team"}</DialogTitle>
            <DialogDescription>The selected lead is also added to the team.</DialogDescription>
          </DialogHeader>
          <Field label="Name" htmlFor="t-name"><Input id="t-name" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Department" htmlFor="t-dept"><Input id="t-dept" value={department} onChange={(e) => setDepartment(e.target.value)} placeholder="e.g. Animation" /></Field>
          <Field label="Team lead" htmlFor="t-lead" hint={leads.data?.length === 0 ? "Create an employee with the Team Lead role first" : undefined}>
            <NativeSelect id="t-lead" value={leadId} onChange={(e) => setLeadId(e.target.value)}>
              <option value="">No lead</option>
              {leads.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name}{u.team && u.team.id !== team?.id ? ` (currently ${u.team.name})` : ""}</option>)}
            </NativeSelect>
          </Field>
          <Field label="Description" htmlFor="t-desc"><Textarea id="t-desc" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending}>{team ? "Save" : "Create team"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
