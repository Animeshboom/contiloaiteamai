import { Megaphone } from "lucide-react"

import { Card } from "@/components/ui/card"
import { formatDateTime } from "@/lib/format"
import { useMyAnnouncements } from "@/lib/queries"

/** Active announcements for the signed-in person (any role). Hidden when there are none or they fail to load. */
export function AnnouncementsFeed() {
  const { data } = useMyAnnouncements()
  if (!data?.length) return null
  return (
    <section className="space-y-2" aria-label="Announcements">
      <h2 className="flex items-center gap-2 text-sm font-semibold"><Megaphone className="size-4 text-primary" />Announcements</h2>
      <div className="grid gap-3 md:grid-cols-2">
        {data.map((a) => (
          <Card key={a.id} className="p-4">
            <div className="font-semibold">{a.title}</div>
            <p className="mt-1 whitespace-pre-line text-sm">{a.body}</p>
            <div className="mt-2 text-xs text-muted-foreground">— {a.author ?? "Studio"} · {formatDateTime(a.created_at)}</div>
          </Card>
        ))}
      </div>
    </section>
  )
}
