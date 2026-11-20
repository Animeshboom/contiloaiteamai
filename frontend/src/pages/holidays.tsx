import { useState, type FormEvent } from "react"
import { ChevronLeft, ChevronRight, Plus, Trash2 } from "lucide-react"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ConfirmDialog, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Checkbox, Field, Input } from "@/components/ui/form-controls"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { formatDate } from "@/lib/format"
import { HOLIDAY_KEYS, useAction, useHolidays, useTeams } from "@/lib/queries"
import type { Holiday } from "@/lib/types"

export default function HolidaysPage() {
  const { config } = useAuth()
  const today = config?.studio_today ?? ""
  const [year, setYear] = useState(() => Number(today.slice(0, 4)) || new Date().getFullYear())
  const [adding, setAdding] = useState(false)
  const [deleteFor, setDeleteFor] = useState<Holiday | null>(null)
  const { data, isLoading, error, refetch } = useHolidays({ year })

  const remove = useAction(() => api.del(`/holidays/${deleteFor!.id}`), {
    success: "Holiday removed", invalidate: HOLIDAY_KEYS, onSuccess: () => setDeleteFor(null),
  })

  return (
    <>
      <PageHeader
        title="Holidays"
        description="Days off for everyone, or only for some teams. Rosters show these days as Day off."
        actions={
          <>
            <div className="flex items-center gap-1">
              <Button variant="outline" size="icon" onClick={() => setYear(year - 1)} aria-label="Previous year"><ChevronLeft /></Button>
              <span className="w-14 text-center font-mono text-sm tabular" aria-label="Year">{year}</span>
              <Button variant="outline" size="icon" onClick={() => setYear(year + 1)} aria-label="Next year"><ChevronRight /></Button>
            </div>
            <Button onClick={() => setAdding(true)}><Plus />Add holiday</Button>
          </>
        }
      />
      {error ? <ErrorState error={error} onRetry={refetch} /> : isLoading ? <LoadingRows /> : !data?.length ? (
        <EmptyState title={`No holidays in ${year}`} description="Add public holidays or team-specific days off."
          action={<Button size="sm" onClick={() => setAdding(true)}><Plus />Add holiday</Button>} />
      ) : (
        <Card className="p-1">
          <Table>
            <TableHeader>
              <TableRow><TableHead>Date</TableHead><TableHead>Name</TableHead><TableHead>Applies to</TableHead><TableHead className="w-10" /></TableRow>
            </TableHeader>
            <TableBody>
              {data.map((h) => (
                <TableRow key={h.id} className={today && h.date < today ? "opacity-55" : ""}>
                  <TableCell className="whitespace-nowrap font-mono text-sm tabular">{formatDate(h.date, true)}</TableCell>
                  <TableCell className="font-medium">{h.name}</TableCell>
                  <TableCell>
                    {h.applies_to_all ? <Badge tone="amber">Everyone</Badge> : (
                      <div className="flex flex-wrap gap-1">{h.teams.map((t) => <Badge key={t.id} tone="blue">{t.name}</Badge>)}</div>
                    )}
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon" className="size-8" onClick={() => setDeleteFor(h)} aria-label={`Delete ${h.name}`}><Trash2 /></Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      {adding && <HolidayDialog defaultDate={today.slice(0, 4) === String(year) ? today : `${year}-01-01`} onClose={() => setAdding(false)} />}
      <ConfirmDialog open={!!deleteFor} onOpenChange={(o) => !o && setDeleteFor(null)} loading={remove.isPending} destructive
        title={`Delete ${deleteFor?.name}?`} confirmLabel="Delete"
        description={deleteFor ? `${formatDate(deleteFor.date, true)} becomes a normal working day again.` : ""}
        onConfirm={() => remove.mutate(undefined)} />
    </>
  )
}

function HolidayDialog({ defaultDate, onClose }: { defaultDate: string; onClose: () => void }) {
  const teams = useTeams()
  const [date, setDate] = useState(defaultDate)
  const [name, setName] = useState("")
  const [scope, setScope] = useState<"all" | "some">("all")
  const [picked, setPicked] = useState<number[]>([])

  const save = useAction(
    () => api.post<Holiday>("/holidays", { date, name: name.trim(), team_ids: scope === "all" ? [] : picked }),
    { success: "Holiday added", invalidate: HOLIDAY_KEYS, onSuccess: onClose },
  )
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(undefined) }
  const toggle = (id: number, on: boolean) => setPicked((p) => (on ? [...p, id] : p.filter((x) => x !== id)))

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Add holiday</DialogTitle>
            <DialogDescription>Nobody is expected to mark attendance on this day.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Date" htmlFor="h-date"><Input id="h-date" type="date" required value={date} onChange={(e) => setDate(e.target.value)} /></Field>
            <Field label="Name" htmlFor="h-name"><Input id="h-name" required minLength={2} maxLength={120} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Diwali" /></Field>
          </div>
          <fieldset className="grid gap-2">
            <legend className="mb-1.5 text-xs font-medium text-muted-foreground">Applies to</legend>
            <label className="flex items-center gap-2 text-sm">
              <input type="radio" name="h-scope" checked={scope === "all"} onChange={() => setScope("all")} />
              Everyone
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="radio" name="h-scope" checked={scope === "some"} onChange={() => setScope("some")} />
              Only some teams
            </label>
          </fieldset>
          {scope === "some" && (
            <div className="max-h-48 space-y-1.5 overflow-y-auto rounded-md border p-3">
              {teams.isLoading ? <LoadingRows rows={2} /> : !teams.data?.length ? (
                <p className="text-sm text-muted-foreground">No teams.</p>
              ) : teams.data.map((b) => (
                <label key={b.id} className="flex items-center gap-2 text-sm">
                  <Checkbox checked={picked.includes(b.id)} onCheckedChange={(c) => toggle(b.id, !!c)} />{b.name}
                </label>
              ))}
            </div>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending} disabled={scope === "some" && picked.length === 0}>Add holiday</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
