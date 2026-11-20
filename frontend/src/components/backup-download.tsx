import { useState } from "react"
import { Download } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api, errorMessage } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"

/** ZIP of the records this person can see (lead: their team; admin: everything). The API allows 6 per hour. */
export function BackupCard() {
  const { user, config } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const day = config?.studio_today ?? new Date().toISOString().slice(0, 10)

  async function download() {
    setBusy(true)
    setError(null)
    try {
      await api.download("/backup", `studiotrack-backup-${day}.zip`)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Backup</CardTitle>
        <CardDescription>
          {user?.role === "admin"
            ? "Saves a copy of all studio records to this computer. Keep it somewhere safe."
            : "Saves a copy of your team's records to this computer. Keep it somewhere safe."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button variant="outline" onClick={download} loading={busy}><Download />Download backup</Button>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  )
}
