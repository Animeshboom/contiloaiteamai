import { useState, type FormEvent } from "react"
import { Megaphone, Trash2 } from "lucide-react"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ConfirmDialog, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Checkbox, Field, Input, Textarea } from "@/components/ui/form-controls"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { formatDate, formatDateTime } from "@/lib/format"
import { useAction, useAnnouncements, useTeams } from "@/lib/queries"
import type { Announcement, TeamRef } from "@/lib/types"

const KEYS = [["announcements"]]

export default function AnnouncementsPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === "admin"
  const teams = useTeams()
  // Leads may only post to teams they lead.
  const myTeams: TeamRef[] = isAdmin ? teams.data ?? [] : (teams.data ?? []).filter((t) => t.lead?.id === user?.id)
  const options = !isAdmin && myTeams.length === 0 && user?.team ? [user.team] : myTeams
  const [expired, setExpired] = useState(false)
  const [creating, setCreating] = useState(false)
  const [deleteFor, setDeleteFor] = useState<Announcement | null>(null)
  const { data, isLoading, error, refetch } = useAnnouncements({ include_expired: expired })
  const remove = useAction(() => api.del(`/announcements/${deleteFor!.id}`), {
    success: "Announcement deleted", invalidate: KEYS, onSuccess: () => setDeleteFor(null),
  })

  return (
    <>
      <PageHeader title="Announcements" description="Notices shown on everyone's home page; each person also gets a notification."
        actions={<Button onClick={() => setCreating(true)} disabled={!isAdmin && options.length === 0}><Megaphone />New announcement</Button>} />
      <div className="mb-4">
        <label className="flex items-center gap-2 text-sm text-muted-foreground"><Checkbox checked={expired} onCheckedChange={(c) => setExpired(!!c)} />Show expired</label>
      </div>
      {error ? <ErrorState error={error} onRetry={refetch} /> : isLoading ? <LoadingRows /> : !data?.length ? (
        <EmptyState title="No announcements" description="Post a notice to your team." />
      ) : (
        <div className="space-y-3">
          {data.map((a) => (
            <Card key={a.id} className={a.active ? "p-4" : "p-4 opacity-60"}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <div className="font-semibold">{a.title}</div>
                  <div className="flex flex-wrap items-center gap-1">
                    {a.applies_to_all ? <Badge tone="amber">Everyone</Badge> : a.teams.map((t) => <Badge key={t.id} tone="blue">{t.name}</Badge>)}
                    {!a.active ? <Badge tone="red">Expired</Badge> : a.show_until && <Badge>until {formatDate(a.show_until)}</Badge>}
                  </div>
                </div>
                {(isAdmin || a.author_id === user?.id) && (
                  <Button variant="ghost" size="icon" className="size-8 shrink-0" onClick={() => setDeleteFor(a)} aria-label={`Delete ${a.title}`}><Trash2 /></Button>
                )}
              </div>
              <p className="mt-2 whitespace-pre-line text-sm">{a.body}</p>
              <div className="mt-2 text-xs text-muted-foreground">{a.author ?? "Unknown"} · {formatDateTime(a.created_at)}</div>
            </Card>
          ))}
        </div>
      )}
      {creating && <AnnouncementDialog isAdmin={isAdmin} teams={options} onClose={() => setCreating(false)} />}
      <ConfirmDialog open={!!deleteFor} onOpenChange={(o) => !o && setDeleteFor(null)} loading={remove.isPending} destructive
        title={`Delete "${deleteFor?.title}"?`} confirmLabel="Delete"
        description="It disappears from home pages. Notifications already delivered stay in the bell."
        onConfirm={() => remove.mutate(undefined)} />
    </>
  )
}

function AnnouncementDialog({ isAdmin, teams, onClose }: { isAdmin: boolean; teams: TeamRef[]; onClose: () => void }) {
  const { config } = useAuth()
  const [title, setTitle] = useState("")
  const [body, setBody] = useState("")
  const [toAll, setToAll] = useState(isAdmin)
  const [picked, setPicked] = useState<number[]>(() => (!isAdmin && teams.length === 1 ? [teams[0].id] : []))
  const [until, setUntil] = useState("")
  const toggle = (id: number, on: boolean) => setPicked((p) => (on ? [...p, id] : p.filter((x) => x !== id)))
  const save = useAction(
    () => api.post<Announcement>("/announcements", {
      title: title.trim(), body: body.trim(), team_ids: toAll ? [] : picked, ...(until ? { show_until: until } : {}),
    }),
    { success: "Announcement posted", invalidate: KEYS, onSuccess: onClose },
  )
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(undefined) }
  const valid = title.trim().length >= 2 && body.trim().length >= 1 && (toAll || picked.length > 0)

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>New announcement</DialogTitle>
            <DialogDescription>Shown on home pages; each person in the audience gets a notification.</DialogDescription>
          </DialogHeader>
          <Field label="Title" htmlFor="an-title"><Input id="an-title" required minLength={2} maxLength={160} value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
          <Field label="Message" htmlFor="an-body"><Textarea id="an-body" required maxLength={4000} rows={5} value={body} onChange={(e) => setBody(e.target.value)} /></Field>
          <fieldset className="grid gap-2">
            <legend className="mb-1.5 text-xs font-medium text-muted-foreground">Audience</legend>
            {isAdmin && (
              <>
                <label className="flex items-center gap-2 text-sm"><input type="radio" name="an-aud" checked={toAll} onChange={() => setToAll(true)} />Everyone</label>
                <label className="flex items-center gap-2 text-sm"><input type="radio" name="an-aud" checked={!toAll} onChange={() => setToAll(false)} />Chosen teams</label>
              </>
            )}
            {!toAll && (
              <div className="max-h-44 space-y-1.5 overflow-y-auto rounded-md border p-3">
                {teams.length === 0 ? <p className="text-sm text-muted-foreground">No teams.</p> : teams.map((t) => (
                  <label key={t.id} className="flex items-center gap-2 text-sm">
                    <Checkbox checked={picked.includes(t.id)} onCheckedChange={(c) => toggle(t.id, !!c)} aria-label={t.name} />{t.name}
                  </label>
                ))}
              </div>
            )}
          </fieldset>
          <Field label="Show until (optional)" htmlFor="an-until" hint="Hidden after this day.">
            <Input id="an-until" type="date" min={config?.studio_today} value={until} onChange={(e) => setUntil(e.target.value)} />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending} disabled={!valid}>Post</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
