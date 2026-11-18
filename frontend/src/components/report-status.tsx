import { Badge } from "@/components/ui/badge"
import type { AiStatus, ReportStatus } from "@/lib/types"

const TONE = { draft: "neutral", approved: "amber", sent: "green", failed: "red" } as const
const LABEL: Record<ReportStatus, string> = { draft: "Draft", approved: "Approved", sent: "Sent", failed: "Send failed" }

export function ReportStatusBadge({ status }: { status: ReportStatus }) {
  return <Badge tone={TONE[status]} dot>{LABEL[status]}</Badge>
}

const AI: Record<AiStatus, { label: string; tone: "green" | "neutral" | "yellow" | "red" }> = {
  generated: { label: "Narrative by Claude", tone: "green" },
  template: { label: "Template narrative", tone: "neutral" },
  rejected_unverified_numbers: { label: "AI narrative discarded", tone: "yellow" },
  ai_error: { label: "AI unavailable — template used", tone: "yellow" },
  refused: { label: "AI declined — template used", tone: "yellow" },
}

export function AiStatusBadge({ status }: { status: AiStatus | null }) {
  if (!status) return null
  const a = AI[status]
  return <Badge tone={a.tone}>{a.label}</Badge>
}
