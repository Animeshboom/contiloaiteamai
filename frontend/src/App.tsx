import type { ReactNode } from "react"
import { Navigate, Route, Routes, useLocation } from "react-router-dom"
import { Loader2 } from "lucide-react"

import { EmptyState } from "@/components/common"
import { AppShell } from "@/components/shell"
import { Button } from "@/components/ui/button"
import { homeFor, useAuth } from "@/lib/auth-context"
import type { Role } from "@/lib/types"
import ArtistDashboardPage from "@/pages/artist-dashboard"
import ArtistsPage from "@/pages/artists"
import AssignmentsPage from "@/pages/assignments"
import EmployeesPage from "@/pages/employees"
import LeadAttendancePage from "@/pages/lead-attendance"
import LoginPage from "@/pages/login"
import NotificationsPage from "@/pages/notifications"
import MyAttendancePage from "@/pages/my-attendance"
import ProjectDetailPage, { EpisodesScenesPage } from "@/pages/project-detail"
import ProjectsPage from "@/pages/projects"
import ReviewsPage from "@/pages/reviews"
import SubmissionsPage from "@/pages/submissions"
import SubmitWorkPage from "@/pages/submit-work"
import SettingsPage from "@/pages/settings"
import StaffOverviewPage from "@/pages/staff-overview"
import TeamsPage from "@/pages/teams"

/** UX guard only — the API enforces every permission independently. */
function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) {
    return <div className="grid min-h-screen place-items-center"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />
  if (!roles.includes(user.role)) return <Navigate to={homeFor(user.role)} replace />
  return <>{children}</>
}

function Home() {
  const { user, loading } = useAuth()
  if (loading) return null
  return <Navigate to={user ? homeFor(user.role) : "/login"} replace />
}

function NotFound() {
  const { user } = useAuth()
  return (
    <div className="grid min-h-[60vh] place-items-center">
      <EmptyState title="Page not found" description="The page you're looking for doesn't exist."
        action={<Button asChild size="sm"><a href={user ? homeFor(user.role) : "/login"}>Go home</a></Button>} />
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Home />} />

      <Route path="/admin" element={<RequireRole roles={["admin"]}><AppShell /></RequireRole>}>
        <Route index element={<StaffOverviewPage />} />
        <Route path="employees" element={<EmployeesPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:id" element={<ProjectDetailPage />} />
        <Route path="teams" element={<TeamsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>

      <Route path="/lead" element={<RequireRole roles={["team_lead"]}><AppShell /></RequireRole>}>
        <Route index element={<StaffOverviewPage />} />
        <Route path="attendance" element={<LeadAttendancePage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:id" element={<ProjectDetailPage />} />
        <Route path="episodes" element={<EpisodesScenesPage />} />
        <Route path="assignments" element={<AssignmentsPage />} />
        <Route path="submissions" element={<SubmissionsPage mode="lead" />} />
        <Route path="reviews" element={<ReviewsPage />} />
        <Route path="artists" element={<ArtistsPage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>

      <Route path="/artist" element={<RequireRole roles={["artist"]}><AppShell /></RequireRole>}>
        <Route index element={<ArtistDashboardPage />} />
        <Route path="attendance" element={<MyAttendancePage />} />
        <Route path="assignments" element={<AssignmentsPage />} />
        <Route path="submit" element={<SubmitWorkPage />} />
        <Route path="reviews" element={<SubmissionsPage key="reviews" mode="artist-reviews" />} />
        <Route path="history" element={<SubmissionsPage key="history" mode="artist-history" />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
