import { useState } from "react"
import { Bell, CheckCheck } from "lucide-react"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common"
import { NotificationItem, useOpenNotification } from "@/components/notifications"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/misc"
import { api } from "@/lib/api"
import { useAction, useNotifications, useUnreadCount } from "@/lib/queries"

export default function NotificationsPage() {
  const [tab, setTab] = useState<"all" | "unread">("all")
  const { data, isLoading, error, refetch } = useNotifications({ unread_only: tab === "unread", limit: 200 })
  const unread = useUnreadCount().data?.unread ?? 0
  const open = useOpenNotification()
  const readAll = useAction(() => api.post<{ updated: number }>("/notifications/read-all"), {
    invalidate: [["notifications"]], success: (r) => `${r.updated} marked as read`,
  })

  return (
    <>
      <PageHeader title="Notifications" description="Assignments, submissions, reviews and deadline reminders."
        actions={unread > 0 && <Button variant="outline" onClick={() => readAll.mutate(undefined)} loading={readAll.isPending}><CheckCheck />Mark all read</Button>} />
      <Tabs value={tab} onValueChange={(v) => setTab(v as "all" | "unread")} className="mb-4">
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="unread">Unread{unread ? ` (${unread})` : ""}</TabsTrigger>
        </TabsList>
      </Tabs>
      {error ? <ErrorState error={error} onRetry={refetch} /> : isLoading ? <LoadingRows /> : !data?.length ? (
        <EmptyState icon={<Bell />} title={tab === "unread" ? "No unread notifications" : "No notifications yet"} />
      ) : (
        <Card className="divide-y p-1">
          {data.map((n) => <NotificationItem key={n.id} n={n} onOpen={open} />)}
        </Card>
      )}
    </>
  )
}
