import { useState, type FormEvent } from "react"
import { KeyRound, MoreHorizontal, Pencil, Plus, Power, Search } from "lucide-react"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ConfirmDialog, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Checkbox, Field, Input, NativeSelect } from "@/components/ui/form-controls"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/misc"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { formatDateTime, titleCase } from "@/lib/format"
import { useAction, useTeams, useUsers } from "@/lib/queries"
import type { Role, User } from "@/lib/types"

const ROLE_TONE = { admin: "red", team_lead: "amber", artist: "blue" } as const

export default function EmployeesPage() {
  const { user: me } = useAuth()
  const [search, setSearch] = useState("")
  const [role, setRole] = useState<Role | "">("")
  const [inactive, setInactive] = useState(false)
  const [dialog, setDialog] = useState<{ user?: User } | null>(null)
  const [resetFor, setResetFor] = useState<User | null>(null)
  const [toggleFor, setToggleFor] = useState<User | null>(null)
  const { data, isLoading, error, refetch } = useUsers({ search: search || undefined, role: role || undefined, include_inactive: inactive })

  const toggle = useAction(
    () => api.post<User>(`/users/${toggleFor!.id}/${toggleFor!.is_active ? "deactivate" : "activate"}`),
    { success: (u) => `${u.full_name} ${u.is_active ? "reactivated" : "deactivated"}`, invalidate: [["users"], ["teams"]], onSuccess: () => setToggleFor(null) },
  )

  return (
    <>
      <PageHeader title="Employees" description="Create accounts, assign roles and teams, and deactivate leavers."
        actions={<Button onClick={() => setDialog({})}><Plus />Add employee</Button>} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input className="w-64 pl-8" placeholder="Search name or email" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search" />
        </div>
        <NativeSelect className="w-40" value={role} onChange={(e) => setRole(e.target.value as Role | "")} aria-label="Role">
          <option value="">All roles</option><option value="admin">Admin</option><option value="team_lead">Team lead</option><option value="artist">Artist</option>
        </NativeSelect>
        <label className="flex items-center gap-2 text-sm text-muted-foreground"><Checkbox checked={inactive} onCheckedChange={(c) => setInactive(!!c)} />Show deactivated</label>
      </div>
      {error ? <ErrorState error={error} onRetry={refetch} /> : isLoading ? <LoadingRows /> : !data?.length ? (
        <EmptyState title="No employees match" />
      ) : (
        <Card className="p-1">
          <Table>
            <TableHeader>
              <TableRow><TableHead>Name</TableHead><TableHead>Role</TableHead><TableHead>Team</TableHead><TableHead>Title</TableHead><TableHead>Last sign-in</TableHead><TableHead className="w-10" /></TableRow>
            </TableHeader>
            <TableBody>
              {data.map((u) => (
                <TableRow key={u.id} className={u.is_active ? "" : "opacity-55"}>
                  <TableCell>
                    <div className="font-medium">{u.full_name}{!u.is_active && <Badge className="ml-2">Deactivated</Badge>}</div>
                    <div className="text-xs text-muted-foreground">{u.email}</div>
                  </TableCell>
                  <TableCell><Badge tone={ROLE_TONE[u.role]}>{titleCase(u.role)}</Badge></TableCell>
                  <TableCell className="text-sm">{u.team?.name ?? "—"}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{u.job_title ?? "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{u.last_login_at ? formatDateTime(u.last_login_at) : "Never"}</TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild><Button variant="ghost" size="icon" className="size-8" aria-label={`Actions for ${u.full_name}`}><MoreHorizontal /></Button></DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onSelect={() => setDialog({ user: u })}><Pencil />Edit</DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => setResetFor(u)}><KeyRound />Reset password</DropdownMenuItem>
                        {u.id !== me?.id && (
                          <DropdownMenuItem destructive={u.is_active} onSelect={() => setToggleFor(u)}><Power />{u.is_active ? "Deactivate" : "Reactivate"}</DropdownMenuItem>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
      {dialog && <EmployeeDialog user={dialog.user} onClose={() => setDialog(null)} />}
      {resetFor && <ResetPasswordDialog user={resetFor} onClose={() => setResetFor(null)} />}
      <ConfirmDialog open={!!toggleFor} onOpenChange={(o) => !o && setToggleFor(null)} loading={toggle.isPending} destructive={toggleFor?.is_active}
        title={toggleFor?.is_active ? `Deactivate ${toggleFor?.full_name}?` : `Reactivate ${toggleFor?.full_name}?`}
        confirmLabel={toggleFor?.is_active ? "Deactivate" : "Reactivate"}
        description={toggleFor?.is_active ? "They will be signed out immediately and cannot sign in. Their history is kept." : "They will be able to sign in again."}
        onConfirm={() => toggle.mutate(undefined)} />
    </>
  )
}

function EmployeeDialog({ user, onClose }: { user?: User; onClose: () => void }) {
  const { user: me } = useAuth()
  const teams = useTeams()
  const [email, setEmail] = useState(user?.email ?? "")
  const [name, setName] = useState(user?.full_name ?? "")
  const [role, setRole] = useState<Role>(user?.role ?? "artist")
  const [teamId, setTeamId] = useState(user?.team ? String(user.team.id) : "")
  const [title, setTitle] = useState(user?.job_title ?? "")
  const [password, setPassword] = useState("")

  const save = useAction(
    () => user
      ? api.patch<User>(`/users/${user.id}`, {
          full_name: name, job_title: title, ...(role !== user.role ? { role } : {}),
          ...(teamId ? { team_id: Number(teamId) } : { clear_team: true }),
        })
      : api.post<User>("/users", { email, full_name: name, role, team_id: teamId ? Number(teamId) : null, job_title: title || null, password }),
    { success: user ? "Employee updated" : "Employee created — share the temporary password securely", invalidate: [["users"], ["teams"]], onSuccess: onClose },
  )
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(undefined) }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{user ? `Edit ${user.full_name}` : "Add employee"}</DialogTitle>
            {user && role !== user.role && <DialogDescription className="text-warning">Changing the role signs this person out so new permissions apply.</DialogDescription>}
          </DialogHeader>
          <Field label="Full name" htmlFor="u-name"><Input id="u-name" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} /></Field>
          {!user && <Field label="Email" htmlFor="u-email"><Input id="u-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Role" htmlFor="u-role">
              <NativeSelect id="u-role" value={role} disabled={user?.id === me?.id} onChange={(e) => setRole(e.target.value as Role)}>
                <option value="artist">Artist</option><option value="team_lead">Team lead</option><option value="admin">Admin</option>
              </NativeSelect>
            </Field>
            <Field label="Team" htmlFor="u-team">
              <NativeSelect id="u-team" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                <option value="">No team</option>
                {teams.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </NativeSelect>
            </Field>
          </div>
          <Field label="Job title" htmlFor="u-title"><Input id="u-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. AI Animator" /></Field>
          {!user && (
            <Field label="Temporary password" htmlFor="u-pw" hint="At least 8 characters. Ask them to change it after first sign-in.">
              <Input id="u-pw" type="text" autoComplete="off" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending}>{user ? "Save" : "Create account"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function ResetPasswordDialog({ user, onClose }: { user: User; onClose: () => void }) {
  const [pw, setPw] = useState("")
  const save = useAction(() => api.post(`/users/${user.id}/reset-password`, { new_password: pw }), {
    success: "Password reset. Existing sessions were signed out.", onSuccess: onClose,
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={(e) => { e.preventDefault(); save.mutate(undefined) }} className="grid gap-4">
          <DialogHeader><DialogTitle>Reset password</DialogTitle><DialogDescription>{user.full_name} · {user.email}</DialogDescription></DialogHeader>
          <Field label="New temporary password" htmlFor="rp"><Input id="rp" required minLength={8} autoComplete="off" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending}>Reset password</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
