import { Link } from "react-router-dom"
import { CalendarClock } from "lucide-react"

import { AssignmentStatusBadge, PriorityBadge, SceneChip } from "@/components/common"
import { Card } from "@/components/ui/card"
import { formatDateTime, relativeDeadline } from "@/lib/format"
import type { Assignment } from "@/lib/types"
import { cn } from "@/lib/utils"

export function AssignmentCard({ assignment: a, viewerId, to }: { assignment: Assignment; viewerId?: number; to: string }) {
  const mine = a.assignees.find((x) => x.user_id === viewerId)
  const status = mine?.status ?? a.status
  const done = status === "approved" || status === "completed"
  const dl = relativeDeadline(a.deadline)
  return (
    <Link to={to} className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-lg">
      <Card className="h-full p-4 transition-colors hover:border-primary/40 hover:bg-accent/30">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="font-mono text-[11px] text-muted-foreground">
              {a.project_code}{a.episode_number != null && ` · EP${String(a.episode_number).padStart(2, "0")}`}
            </div>
            <div className="mt-0.5 truncate font-medium">{a.title}</div>
          </div>
          <PriorityBadge priority={a.priority} />
        </div>
        {a.scenes.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1">
            {a.scenes.slice(0, 8).map((s) => <SceneChip key={s.id} label={s.label} />)}
            {a.scenes.length > 8 && <SceneChip label={`+${a.scenes.length - 8}`} />}
          </div>
        )}
        <div className="mt-3 flex items-center justify-between gap-2 text-xs">
          <AssignmentStatusBadge status={status} />
          <span className={cn("inline-flex items-center gap-1 text-muted-foreground", !done && dl.overdue && "text-destructive")} title={formatDateTime(a.deadline)}>
            <CalendarClock className="size-3.5" />
            {done ? formatDateTime(a.deadline) : dl.text}
          </span>
        </div>
      </Card>
    </Link>
  )
}
