import { Suspense, lazy, type ReactNode } from "react"
import { Navigate, Route, Routes, useLocation } from "react-router-dom"
import { Loader2 } from "lucide-react"

import { EmptyState } from "@/components/common"
import { AppShell } from "@/components/shell"
import { Button } from "@/components/ui/button"
import { homeFor, useAuth } from "@/lib/auth-context"
import type { Role } from "@/lib/types"
const ArtistDashboardPage = lazy(() => import("@/pages/artist-dashboard"))
const ArtistsPage = lazy(() => import("@/pages/artists"))
const AssignmentsPage = lazy(() => import("@/pages/assignments"))
const EmployeesPage = lazy(() => import("@/pages/employees"))
const LeadAttendancePage = lazy(() => import("@/pages/lead-attendance"))
import LoginPage from "@/pages/login"
const NotificationsPage = lazy(() => import("@/pages/notifications"))
const MyAttendancePage = lazy(() => import("@/pages/my-attendance"))
const ProjectDetailPage = lazy(() => import("@/pages/project-detail"))
const EpisodesScenesPage = lazy(() => import("@/pages/project-detail").then((mod) => ({ default: mod.EpisodesScenesPage })))
const ProjectsPage = lazy(() => import("@/pages/projects"))
const ReportDetailPage = lazy(() => import("@/pages/report-detail"))
const ReportsPage = lazy(() => import("@/pages/reports"))
const ReviewsPage = lazy(() => import("@/pages/reviews"))
const SubmissionsPage = lazy(() => import("@/pages/submissions"))
const SubmitWorkPage = lazy(() => import("@/pages/submit-work"))
const SettingsPage = lazy(() => import("@/pages/settings"))
const StaffOverviewPage = lazy(() => import("@/pages/staff-overview"))
const TeamsPage = lazy(() => import("@/pages/teams"))

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

function PageLoading() {
  return <div className="grid min-h-[50vh] place-items-center"><Loader2 className="size-6 animate-spin text-muted-foreground" aria-label="Loading" /></div>
}

export default function App() {
  return (
    <Suspense fallback={<PageLoading />}>
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Home />} />

      <Route path="/admin" element={<RequireRole roles={["admin"]}><AppShell /></RequireRole>}>
        <Route index element={<StaffOverviewPage />} />
        <Route path="employees" element={<EmployeesPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:id" element={<ProjectDetailPage />} />
        <Route path="teams" element={<TeamsPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="reports/:id" element={<ReportDetailPage />} />
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
        <Route path="reports" element={<ReportsPage />} />
        <Route path="reports/:id" element={<ReportDetailPage />} />
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
    </Suspense>
  )
}
