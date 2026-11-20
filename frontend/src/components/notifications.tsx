import { useNavigate } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { AlarmClock, Bell, CheckCheck, CheckCircle2, ClipboardList, FileText, Inbox, Megaphone, RotateCcw, ShieldAlert } from "lucide-react"

import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/misc"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { formatDateTime } from "@/lib/format"
import { keys, useAction, useNotifications, useUnreadCount } from "@/lib/queries"
import type { AppNotification } from "@/lib/types"
import { cn } from "@/lib/utils"

const ICONS: Record<string, React.ReactNode> = {
  assignment_created: <ClipboardList className="text-info" />,
  submission_received: <Inbox className="text-primary" />,
  submission_approved: <CheckCircle2 className="text-success" />,
  revision_requested: <RotateCcw className="text-destructive" />,
  deadline_approaching: <AlarmClock className="text-warning" />,
  daily_report_generated: <FileText className="text-primary" />,
  security_alert: <ShieldAlert className="text-destructive" />,
  announcement: <Megaphone className="text-primary" />,  // links to the person's home, where the feed is on top  // links to /admin/activity
}

export function notificationsPath(role?: string) {
  return role === "artist" ? "/artist/notifications" : role === "team_lead" ? "/lead/notifications" : null
}

/** Marks a notification read and follows its link. */
export function useOpenNotification() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const read = useAction((id: number) => api.post(`/notifications/${id}/read`), { invalidate: [["notifications"]] })
  return (n: AppNotification) => {
    if (!n.read_at) read.mutate(n.id)
    if (n.event_type === "announcement") {
      void qc.invalidateQueries({ queryKey: keys.myAnnouncements })  // show it now, not at the next poll
      try { window.scrollTo({ top: 0, behavior: "smooth" }) } catch { /* not supported */ }
    }
    if (n.link) navigate(n.link)
  }
}

export function NotificationItem({ n, onOpen, compact }: { n: AppNotification; onOpen: (n: AppNotification) => void; compact?: boolean }) {
  return (
    <button type="button" onClick={() => onOpen(n)}
      className={cn("flex w-full gap-3 rounded-md px-3 py-2.5 text-left transition-colors hover:bg-accent cursor-pointer", !n.read_at && "bg-primary/5")}>
      <span className="mt-0.5 shrink-0 [&_svg]:size-4">{ICONS[n.event_type] ?? <Bell className="text-muted-foreground" />}</span>
      <span className="min-w-0 flex-1">
        <span className={cn("block truncate text-sm", !n.read_at && "font-medium")}>{n.title}</span>
        <span className={cn("block text-xs text-muted-foreground", compact ? "truncate" : "whitespace-pre-wrap")}>{n.message}</span>
        <span className="mt-0.5 block text-[11px] text-muted-foreground/80">{formatDateTime(n.created_at)}</span>
      </span>
      {!n.read_at && <span className="mt-1.5 size-2 shrink-0 rounded-full bg-primary" aria-label="Unread" />}
    </button>
  )
}

export function NotificationBell() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const count = useUnreadCount()
  const list = useNotifications({ limit: 8 })
  const open = useOpenNotification()
  const readAll = useAction(() => api.post("/notifications/read-all"), { invalidate: [["notifications"]] })
  const unread = count.data?.unread ?? 0
  const allPath = notificationsPath(user?.role)

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}>
          <Bell />
          {unread > 0 && (
            <span className="absolute -right-0.5 -top-0.5 grid min-w-4 place-items-center rounded-full bg-primary px-1 font-mono text-[10px] font-semibold text-primary-foreground">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[min(24rem,calc(100vw-1rem))] p-0">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <span className="text-sm font-semibold">Notifications</span>
          {unread > 0 && <Button variant="ghost" size="sm" disabled={readAll.isPending} onClick={() => readAll.mutate(undefined)}><CheckCheck />Mark all read</Button>}
        </div>
        <div className="max-h-96 overflow-y-auto p-1">
          {!list.data?.length ? (
            <p className="px-3 py-8 text-center text-sm text-muted-foreground">You're all caught up.</p>
          ) : list.data.map((n) => <NotificationItem key={n.id} n={n} onOpen={open} compact />)}
        </div>
        {allPath && (
          <div className="border-t p-1">
            <Button variant="ghost" size="sm" className="w-full" onClick={() => navigate(allPath)}>View all notifications</Button>
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
