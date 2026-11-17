import { Link } from "react-router-dom"
import { AlarmClock, ClipboardList, Hourglass } from "lucide-react"

import { CheckInCard } from "@/components/check-in-card"
import { AssignmentCard } from "@/components/assignment-card"
import { EmptyState, ErrorState, LoadingRows, PageHeader, StatCard } from "@/components/common"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/lib/auth-context"
import { useArtistOverview, useAssignments } from "@/lib/queries"

export default function ArtistDashboardPage() {
  const { user } = useAuth()
  const overview = useArtistOverview()
  const assignments = useAssignments()
  const open = (assignments.data ?? []).filter((a) => {
    const mine = a.assignees.find((x) => x.user_id === user?.id)
    return mine && ["assigned", "in_progress", "revision_required"].includes(mine.status)
  })

  return (
    <>
      <PageHeader title={`Hello, ${user?.full_name.split(" ")[0]}`} description="Your day at a glance." />
      <div className="space-y-6">
        <CheckInCard />
        {overview.data && (
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Open assignments" icon={<ClipboardList />} value={overview.data.open_assignments} tone="amber" />
            <StatCard label="Awaiting review" icon={<Hourglass />} value={overview.data.awaiting_review} />
            <StatCard label="Overdue" icon={<AlarmClock />} value={overview.data.overdue} tone={overview.data.overdue ? "red" : "default"} />
          </div>
        )}
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Up next</h2>
            <Button asChild variant="ghost" size="sm"><Link to="/artist/assignments">View all</Link></Button>
          </div>
          {assignments.error ? <ErrorState error={assignments.error} onRetry={assignments.refetch} /> : assignments.isLoading ? <LoadingRows rows={3} /> :
            open.length === 0 ? <EmptyState title="No open assignments" description="New work from your team lead will appear here." /> : (
              <div className="grid gap-3 md:grid-cols-2">
                {open.slice(0, 4).map((a) => <AssignmentCard key={a.id} assignment={a} viewerId={user?.id} to={`/artist/assignments?open=${a.id}`} />)}
              </div>
            )}
        </div>
      </div>
    </>
  )
}
