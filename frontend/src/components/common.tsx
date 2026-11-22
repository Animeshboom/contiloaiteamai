import type { ReactNode } from "react"
import { AlertTriangle, Inbox } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/misc"
import { errorMessage } from "@/lib/api"
import { titleCase } from "@/lib/format"
import type { AssignmentStatus, AttendanceStatus, HalfDayType, LeaveStatus, LeaveType, Priority, ProjectStatus, WorkStatus } from "@/lib/types"
import { cn } from "@/lib/utils"

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function StatCard({ label, value, hint, tone = "default", icon }: {
  label: string; value: ReactNode; hint?: ReactNode; tone?: "default" | "amber" | "red" | "green" | "blue"; icon?: ReactNode
}) {
  const accent = {
    default: "text-foreground", amber: "text-primary", red: "text-destructive", green: "text-success", blue: "text-info",
  }[tone]
  return (
    <Card className="relative overflow-hidden p-4">
      <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
        <span>{label}</span>
        {icon && <span className="text-muted-foreground/70 [&_svg]:size-4">{icon}</span>}
      </div>
      <div className={cn("mt-2 font-mono text-2xl font-medium tabular", accent)}>{value}</div>
      {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
    </Card>
  )
}

export function EmptyState({ title, description, action, icon }: { title: string; description?: string; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-12 text-center">
      <div className="mb-1 rounded-full bg-muted p-3 text-muted-foreground [&_svg]:size-5">{icon ?? <Inbox />}</div>
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="max-w-sm text-xs text-muted-foreground">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-6 py-10 text-center">
      <AlertTriangle className="size-5 text-destructive" />
      <p className="text-sm">{errorMessage(error)}</p>
      {onRetry && <Button variant="outline" size="sm" onClick={onRetry}>Try again</Button>}
    </div>
  )
}

export function LoadingRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-1" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
    </div>
  )
}

/* ---------- status badges ---------- */

type Tone = "neutral" | "amber" | "blue" | "green" | "red" | "yellow"

const ASSIGNMENT_TONE: Record<AssignmentStatus, Tone> = {
  assigned: "neutral", in_progress: "blue", submitted: "amber", approved: "green", revision_required: "red", completed: "green",
  reassigned: "neutral",
}
const ASSIGNMENT_LABEL: Record<AssignmentStatus, string> = {
  assigned: "Assigned", in_progress: "In Progress", submitted: "In Review", approved: "Approved",
  revision_required: "Revision Required", completed: "Completed", reassigned: "Reassigned",
}
export function AssignmentStatusBadge({ status }: { status: AssignmentStatus }) {
  return <Badge tone={ASSIGNMENT_TONE[status]} dot>{ASSIGNMENT_LABEL[status]}</Badge>
}
export const assignmentStatusLabel = (s: AssignmentStatus) => ASSIGNMENT_LABEL[s]

const ATTENDANCE_TONE: Record<AttendanceStatus | "not_checked_in" | "day_off", Tone> = {
  present: "green", half_day: "yellow", leave: "blue", absent: "red", not_checked_in: "neutral", day_off: "neutral",
}
export function AttendanceBadge({ status }: { status: AttendanceStatus | "not_checked_in" | "day_off" }) {
  return <Badge tone={ATTENDANCE_TONE[status]} dot>{status === "not_checked_in" ? "Not checked in" : status === "day_off" ? "Day off" : titleCase(status)}</Badge>
}

const LEAVE_TONE: Record<LeaveStatus, Tone> = { pending: "yellow", approved: "green", rejected: "red", cancelled: "neutral" }
export function LeaveStatusBadge({ status }: { status: LeaveStatus }) {
  return <Badge tone={LEAVE_TONE[status] ?? "neutral"}>{titleCase(status)}</Badge>
}

const LEAVE_TYPE_META: Record<LeaveType, { label: string; tone: Tone }> = {
  casual: { label: "Casual (CL)", tone: "blue" },
  sick: { label: "Sick (SL)", tone: "amber" },
  privilege: { label: "Vacation (PL)", tone: "green" },
  unpaid: { label: "Unpaid (LOP)", tone: "red" },
}

export function LeaveTypeBadge({ type, halfDay }: { type?: LeaveType; halfDay?: HalfDayType | null }) {
  const meta = LEAVE_TYPE_META[type ?? "casual"] ?? LEAVE_TYPE_META.casual
  return (
    <span className="inline-flex items-center gap-1">
      <Badge tone={meta.tone}>{meta.label}</Badge>
      {halfDay && (
        <Badge tone="neutral" className="text-[10px]">
          {halfDay === "first_half" ? "1st Half" : "2nd Half"}
        </Badge>
      )}
    </span>
  )
}

const PRIORITY_TONE: Record<Priority, Tone> = { low: "neutral", medium: "blue", high: "amber", urgent: "red" }
export function PriorityBadge({ priority }: { priority: Priority }) {
  return <Badge tone={PRIORITY_TONE[priority]}>{titleCase(priority)}</Badge>
}

const PROJECT_TONE: Record<ProjectStatus, Tone> = {
  planning: "neutral", active: "green", on_hold: "yellow", completed: "blue", archived: "neutral",
}
export function ProjectStatusBadge({ status }: { status: ProjectStatus }) {
  return <Badge tone={PROJECT_TONE[status]} dot>{titleCase(status)}</Badge>
}

const WORK_TONE: Record<WorkStatus, Tone> = {
  not_started: "neutral", in_progress: "blue", in_review: "amber", approved: "green", completed: "green",
}
export function WorkStatusBadge({ status }: { status: WorkStatus }) {
  return <Badge tone={WORK_TONE[status]}>{titleCase(status)}</Badge>
}

export function SceneChip({ label, className }: { label: string; className?: string }) {
  return <span className={cn("inline-flex rounded border bg-muted/60 px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground", className)}>{label}</span>
}
