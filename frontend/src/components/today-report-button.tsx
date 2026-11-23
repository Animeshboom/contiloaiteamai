import { useNavigate } from "react-router-dom"
import { FileText, Sparkles } from "lucide-react"

import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { useAction, useReports } from "@/lib/queries"
import type { Report } from "@/lib/types"

/** Team lead: open today's EOD report, or generate it if there isn't one yet. */
export function TodayReportButton() {
  const { user, config } = useAuth()
  const navigate = useNavigate()
  const reports = useReports()
  const today = config?.studio_today
  const mine = (reports.data ?? []).find((r) => r.report_date === today && r.created_by_name === user?.full_name)

  const generate = useAction(
    () => api.post<Report>("/reports", { report_date: today, use_ai: !!config?.ai_enabled }),
    { success: "Today's report drafted — add your notes, then send it", invalidate: [["reports"]],
      onSuccess: (r) => navigate(`/lead/reports/${r.id}`) },
  )

  if (mine) {
    return (
      <Button variant="outline" onClick={() => navigate(`/lead/reports/${mine.id}`)}>
        <FileText />{mine.submitted_at || mine.status === "sent" ? "Today's report (sent)" : "Open today's report"}
      </Button>
    )
  }
  return (
    <Button variant="outline" loading={generate.isPending} disabled={reports.isLoading || !today}
      onClick={() => generate.mutate(undefined)}>
      <Sparkles />Generate today's report
    </Button>
  )
}
