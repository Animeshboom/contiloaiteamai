import { useState } from "react"
import { Download } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input, NativeSelect } from "@/components/ui/form-controls"
import { api, errorMessage } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { useTeams } from "@/lib/queries"

/** Staff monthly attendance CSV (P/H/L/A/-/off per day plus totals). Admins can pick a team; leads get their own team(s). */
export function StaffAttendanceExport() {
  const { user, config } = useAuth()
  const isAdmin = user?.role === "admin"
  const thisMonth = (config?.studio_today ?? "").slice(0, 7)
  const [month, setMonth] = useState(thisMonth)
  const [teamId, setTeamId] = useState("")
  const [busy, setBusy] = useState(false)
  const teams = useTeams()

  async function download() {
    setBusy(true)
    try {
      const q = new URLSearchParams({ month })
      if (teamId) q.set("team_id", teamId)
      const team = teams.data?.find((t) => String(t.id) === teamId)?.name
      const slug = team ? `-${team.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}` : ""
      await api.download(`/attendance/export?${q}`, `staff-attendance-${month}${slug}.csv`)
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Input type="month" className="w-40" value={month} max={thisMonth} onChange={(e) => setMonth(e.target.value)} aria-label="Export month" />
      {isAdmin && (
        <NativeSelect className="w-44" value={teamId} onChange={(e) => setTeamId(e.target.value)} aria-label="Export team">
          <option value="">All teams</option>
          {teams.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </NativeSelect>
      )}
      <Button variant="outline" loading={busy} disabled={!/^\d{4}-\d{2}$/.test(month)} onClick={download}><Download />Download CSV</Button>
    </div>
  )
}
