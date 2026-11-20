import { useState, type FormEvent } from "react"
import { Target } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Field, Input } from "@/components/ui/form-controls"
import { api } from "@/lib/api"
import { formatDate } from "@/lib/format"
import { useAction, useMyTarget } from "@/lib/queries"
import type { WeeklyTarget } from "@/lib/types"
import { cn } from "@/lib/utils"

export function ProgressBar({ value, max, className }: { value: number; max: number; className?: string }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-muted", className)} role="progressbar"
      aria-valuemin={0} aria-valuemax={max} aria-valuenow={value}>
      <div className={cn("h-full rounded-full", value >= max ? "bg-success" : "bg-primary")} style={{ width: `${pct}%` }} />
    </div>
  )
}

/** Artist home: this week's approved scenes against the target. Hidden when no target is set. */
export function WeeklyTargetBar() {
  const { data } = useMyTarget()
  if (!data || data.target == null) return null
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className="flex items-center gap-2"><Target className="size-4 text-primary" />
          <span>This week: <span className="font-semibold">{data.approved} / {data.target}</span> scenes approved</span>
        </span>
        <span className="text-xs text-muted-foreground">{formatDate(data.week_start)} – {formatDate(data.week_end)}</span>
      </div>
      <ProgressBar className="mt-2" value={data.approved} max={data.target} />
    </Card>
  )
}

/** Lead/admin: set or clear someone's weekly scene target. */
export function TargetDialog({ userId, name, current, onClose }: { userId: number; name: string; current: number | null; onClose: () => void }) {
  const [value, setValue] = useState(current != null ? String(current) : "")
  const save = useAction(
    (target: number | null) => api.put<WeeklyTarget>(`/targets/${userId}`, { scenes_per_week: target }),
    { success: (r) => (r.target == null ? "Target cleared" : `Target set to ${r.target} scenes a week`), invalidate: [["dashboard"]], onSuccess: onClose },
  )
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(value ? Number(value) : null) }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Weekly target</DialogTitle>
            <DialogDescription>{name} · approved scenes per week (Mon–Sun)</DialogDescription>
          </DialogHeader>
          <Field label="Scenes per week" htmlFor="tg-n" hint="Leave empty to clear the target.">
            <Input id="tg-n" type="number" inputMode="numeric" min={1} max={200} value={value} onChange={(e) => setValue(e.target.value)} />
          </Field>
          <DialogFooter>
            {current != null && <Button type="button" variant="ghost" disabled={save.isPending} onClick={() => save.mutate(null)}>Clear target</Button>}
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending}>Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
