import { useState, type ReactNode } from "react"
import { NavLink, Outlet, useNavigate } from "react-router-dom"
import {
  Building2, CalendarCheck, ChevronDown, ClipboardList, Clapperboard, Film, KeyRound, LayoutDashboard, LogOut, Menu,
  History, Inbox, ListChecks, MessageSquareText, Send, Settings, UserCircle2, Users, X,
} from "lucide-react"

import { ChangePasswordDialog } from "@/components/change-password"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/misc"
import { useAuth } from "@/lib/auth-context"
import { useSubmissions } from "@/lib/queries"
import { getStudioTimezone, initials, titleCase } from "@/lib/format"
import type { Role } from "@/lib/types"
import { cn } from "@/lib/utils"

interface NavItem { to: string; label: string; icon: ReactNode; end?: boolean; badge?: "reviews" }

/** Only routes that are implemented appear here — no placeholder links. */
export const NAV: Record<Role, NavItem[]> = {
  admin: [
    { to: "/admin", label: "Overview", icon: <LayoutDashboard />, end: true },
    { to: "/admin/employees", label: "Employees", icon: <Users /> },
    { to: "/admin/projects", label: "Projects", icon: <Film /> },
    { to: "/admin/teams", label: "Teams", icon: <Building2 /> },
    { to: "/admin/settings", label: "Settings", icon: <Settings /> },
  ],
  team_lead: [
    { to: "/lead", label: "Overview", icon: <LayoutDashboard />, end: true },
    { to: "/lead/attendance", label: "Attendance", icon: <CalendarCheck /> },
    { to: "/lead/projects", label: "Projects", icon: <Film /> },
    { to: "/lead/episodes", label: "Episodes & Scenes", icon: <Clapperboard /> },
    { to: "/lead/assignments", label: "Assignments", icon: <ClipboardList /> },
    { to: "/lead/submissions", label: "Submissions", icon: <Inbox /> },
    { to: "/lead/reviews", label: "Reviews", icon: <ListChecks />, badge: "reviews" },
    { to: "/lead/artists", label: "Artists", icon: <Users /> },
    { to: "/lead/settings", label: "Settings", icon: <Settings /> },
  ],
  artist: [
    { to: "/artist", label: "My Dashboard", icon: <LayoutDashboard />, end: true },
    { to: "/artist/attendance", label: "My Attendance", icon: <CalendarCheck /> },
    { to: "/artist/assignments", label: "My Assignments", icon: <ClipboardList /> },
    { to: "/artist/submit", label: "Submit Work", icon: <Send /> },
    { to: "/artist/reviews", label: "My Reviews", icon: <MessageSquareText /> },
    { to: "/artist/history", label: "Work History", icon: <History /> },
  ],
}

const ROLE_LABEL: Record<Role, string> = { admin: "Administrator", team_lead: "Team Lead", artist: "Artist" }

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <div className="grid size-8 place-items-center rounded-md border border-primary/40 bg-primary/10 text-primary">
        <Clapperboard className="size-4" />
      </div>
      <div className="leading-tight">
        <div className="text-sm font-semibold tracking-tight">StudioTrack</div>
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Production · AI</div>
      </div>
    </div>
  )
}

function SidebarNav({ role, onNavigate }: { role: Role; onNavigate?: () => void }) {
  const pending = useSubmissions({ status: "pending_review" }, role === "team_lead")
  const counts = { reviews: pending.data?.length ?? 0 }
  return (
    <nav className="flex flex-col gap-0.5">
      {NAV[role].map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "group relative flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground [&_svg]:size-4",
              isActive && "bg-accent text-foreground before:absolute before:left-0 before:top-1.5 before:bottom-1.5 before:w-0.5 before:rounded-full before:bg-primary",
            )
          }
        >
          {item.icon}
          {item.label}
          {item.badge && counts[item.badge] > 0 && (
            <span className="ml-auto rounded-full bg-primary px-1.5 font-mono text-[10px] font-semibold text-primary-foreground" aria-label={`${counts[item.badge]} pending`}>
              {counts[item.badge]}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  )
}

export function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [pwOpen, setPwOpen] = useState(false)
  if (!user) return null

  const sidebar = (
    <div className="flex h-full flex-col gap-6 px-3 py-4">
      <Brand />
      <div className="px-2.5 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground/70">{ROLE_LABEL[user.role]} workspace</div>
      <SidebarNav role={user.role} onNavigate={() => setMobileOpen(false)} />
      <div className="mt-auto rounded-md border bg-card/60 p-3 text-[11px] text-muted-foreground">
        <div className="font-mono uppercase tracking-wider">Studio time</div>
        <div className="mt-0.5 text-foreground">{getStudioTimezone()}</div>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 border-r bg-sidebar lg:block">{sidebar}</aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 border-r bg-sidebar">
            <button className="absolute right-3 top-4 text-muted-foreground cursor-pointer" onClick={() => setMobileOpen(false)} aria-label="Close menu">
              <X className="size-5" />
            </button>
            {sidebar}
          </aside>
        </div>
      )}

      <div className="lg:pl-60">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b bg-background/85 px-4 backdrop-blur lg:px-8">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu">
            <Menu />
          </Button>
          <div className="flex-1" />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-accent cursor-pointer">
                <div className="grid size-7 place-items-center rounded-full bg-primary/15 text-[11px] font-semibold text-primary">{initials(user.full_name)}</div>
                <div className="hidden leading-tight sm:block">
                  <div className="text-sm font-medium">{user.full_name}</div>
                  <div className="text-[11px] text-muted-foreground">{titleCase(user.role)}{user.team ? ` · ${user.team.name}` : ""}</div>
                </div>
                <ChevronDown className="size-4 text-muted-foreground" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel>
                <div className="flex items-center gap-2"><UserCircle2 className="size-4" />{user.email}</div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setPwOpen(true)}><KeyRound />Change password</DropdownMenuItem>
              <DropdownMenuItem destructive onSelect={() => { logout(); navigate("/login") }}><LogOut />Sign out</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>
      <ChangePasswordDialog open={pwOpen} onOpenChange={setPwOpen} />
    </div>
  )
}
