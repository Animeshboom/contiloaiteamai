import { useState, type FormEvent } from "react"
import { FileUp, KeyRound, LockOpen, MoreHorizontal, Pencil, Plus, Power, Search, ShieldOff, UserPlus } from "lucide-react"

import { StaffAttendanceExport } from "@/components/attendance-export"
import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common"
import { CredentialsDialog } from "@/components/credentials-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ConfirmDialog, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Checkbox, Field, Input, NativeSelect } from "@/components/ui/form-controls"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/misc"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, errorMessage } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { formatDateTime, titleCase } from "@/lib/format"
import { importArtistsCsv } from "@/lib/credentials"
import { useAction, useTeams, useUsers } from "@/lib/queries"
import type { Credentials, ImportResult, Role, User } from "@/lib/types"

const ROLE_TONE = { admin: "red", team_lead: "amber", artist: "blue" } as const
const USER_KEYS = [["users"], ["teams"]]

type Shown = { title: string; creds: Credentials[]; errors?: ImportResult["errors"] }

/** Locked after too many wrong passwords (the lock simply expires; an admin can lift it early). */
const isLocked = (u: User) => !!u.locked_until && new Date(u.locked_until).getTime() > Date.now()

export default function EmployeesPage() {
  const { user: me } = useAuth()
  const [search, setSearch] = useState("")
  const [role, setRole] = useState<Role | "">("")
  const [inactive, setInactive] = useState(false)
  const [dialog, setDialog] = useState<{ user?: User } | null>(null)
  const [resetFor, setResetFor] = useState<User | null>(null)
  const [toggleFor, setToggleFor] = useState<User | null>(null)
  const [addArtist, setAddArtist] = useState(false)
  const [importing, setImporting] = useState(false)
  const [artistReset, setArtistReset] = useState<User | null>(null)
  const [shown, setShown] = useState<Shown | null>(null)
  const [twoStepFor, setTwoStepFor] = useState<User | null>(null)
  const unlock = useAction((u: User) => api.post<User>(`/users/${u.id}/unlock`), {
    success: (u) => `${u.full_name} can sign in again`, invalidate: [["users"]],
  })
  const resetTwoStep = useAction(() => api.post<User>(`/users/${twoStepFor!.id}/reset-two-step`), {
    success: (u) => `Two-step login reset for ${u.full_name}`, invalidate: [["users"]], onSuccess: () => setTwoStepFor(null),
  })
  const resetArtist = useAction(
    () => api.post<Credentials>(`/artists/${artistReset!.id}/reset-password`),
    { invalidate: USER_KEYS, onSuccess: (c) => { setArtistReset(null); setShown({ title: `New password for ${c.user.full_name}`, creds: [c] }) } },
  )
  const { data, isLoading, error, refetch } = useUsers({ search: search || undefined, role: role || undefined, include_inactive: inactive })

  const toggle = useAction(
    () => api.post<User>(`/users/${toggleFor!.id}/${toggleFor!.is_active ? "deactivate" : "activate"}`),
    { success: (u) => `${u.full_name} ${u.is_active ? "reactivated" : "deactivated"}`, invalidate: [["users"], ["teams"]], onSuccess: () => setToggleFor(null) },
  )

  return (
    <>
      <PageHeader title="Employees" description="Create accounts, assign roles and teams, and deactivate leavers."
        actions={
          <>
            <Button variant="outline" onClick={() => setDialog({})}><Plus />Add lead / admin</Button>
            <Button variant="outline" onClick={() => setImporting(true)}><FileUp />Import artists</Button>
            <Button onClick={() => setAddArtist(true)}><UserPlus />Add artist</Button>
          </>
        } />
      <Card className="mb-4 flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-sm font-medium">Staff attendance export</div>
          <div className="text-xs text-muted-foreground">Monthly CSV: one column per day (P / H / L / A / - / off), totals, hours and attendance %.</div>
        </div>
        <StaffAttendanceExport />
      </Card>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input className="w-64 pl-8" placeholder="Search name, email or ID" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search" />
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
                    <div className="font-medium">
                      {u.full_name}{!u.is_active && <Badge className="ml-2">Deactivated</Badge>}
                      {isLocked(u) && <Badge tone="red" className="ml-2" title={`Locked until ${formatDateTime(u.locked_until!)}`}>Locked</Badge>}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {u.employee_code ? <span className="font-mono">{u.employee_code}</span> : u.email}{u.phone ? ` · ${u.phone}` : ""}
                    </div>
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
                        <DropdownMenuItem onSelect={() => (u.role === "artist" ? setArtistReset(u) : setResetFor(u))}><KeyRound />Reset password</DropdownMenuItem>
                        {isLocked(u) && <DropdownMenuItem disabled={unlock.isPending} onSelect={() => unlock.mutate(u)}><LockOpen />Unlock</DropdownMenuItem>}
                        {u.role === "admin" && u.mfa_enabled && u.id !== me?.id && (
                          <DropdownMenuItem destructive onSelect={() => setTwoStepFor(u)}><ShieldOff />Reset two-step login</DropdownMenuItem>
                        )}
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
      {addArtist && (
        <ArtistDialog onClose={() => setAddArtist(false)}
          onCreated={(c) => { setAddArtist(false); setShown({ title: `Account created for ${c.user.full_name}`, creds: [c] }) }} />
      )}
      {importing && (
        <ImportArtistsDialog onClose={() => setImporting(false)}
          onDone={(r) => { setImporting(false); setShown({ title: `Imported ${r.created.length} artist${r.created.length === 1 ? "" : "s"}`, creds: r.created, errors: r.errors }) }} />
      )}
      {shown && <CredentialsDialog title={shown.title} creds={shown.creds} errors={shown.errors} onClose={() => setShown(null)} />}
      <ConfirmDialog open={!!artistReset} onOpenChange={(o) => !o && setArtistReset(null)} loading={resetArtist.isPending}
        title={`Reset password for ${artistReset?.full_name}?`} confirmLabel="Reset password"
        description="A new password is generated and shown once. The old one stops working and they are signed out."
        onConfirm={() => resetArtist.mutate(undefined)} />
      <ConfirmDialog open={!!twoStepFor} onOpenChange={(o) => !o && setTwoStepFor(null)} loading={resetTwoStep.isPending} destructive
        title={`Reset two-step login for ${twoStepFor?.full_name}?`} confirmLabel="Reset two-step login"
        description="Use this when they lost their phone. Their authenticator code stops working and they set up two-step login again at their next sign-in."
        onConfirm={() => resetTwoStep.mutate(undefined)} />
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

function ArtistDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (c: Credentials) => void }) {
  const teams = useTeams()
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [code, setCode] = useState("")
  const [teamId, setTeamId] = useState("")
  const [title, setTitle] = useState("Artist")
  const [phone, setPhone] = useState("")
  const [password, setPassword] = useState("")
  const save = useAction(
    () => api.post<Credentials>("/artists", {
      full_name: name.trim(), email: email.trim() || null, employee_code: code.trim() || null,
      team_id: teamId ? Number(teamId) : null, job_title: title.trim() || null, phone: phone.trim() || null, password: password || null,
    }),
    { invalidate: USER_KEYS, onSuccess: onCreated },
  )
  // Same rules as the server, shown while typing instead of after pressing Create.
  const pwError = password && password.length < 8 ? `At least 8 characters (now ${password.length})` : undefined
  const phoneError = phone.trim() && !/^\+?[0-9 ()-]{6,24}$/.test(phone.trim()) ? "Digits, spaces, + ( ) - only (6–24)" : undefined
  const bothError = email.trim() && code.trim() ? "Use either an email or an Employee ID, not both" : undefined
  const invalid = name.trim().length < 2 || !!pwError || !!phoneError || !!bothError
  const submit = (e: FormEvent) => { e.preventDefault(); if (!invalid) save.mutate(undefined) }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4" noValidate>
          <DialogHeader>
            <DialogTitle>Add artist</DialogTitle>
            <DialogDescription>Give an email or an Employee ID (not both). Leave both empty for an automatic ID (EMP001, EMP002...).</DialogDescription>
          </DialogHeader>
          <Field label="Full name" htmlFor="ar-name"><Input id="ar-name" required minLength={2} maxLength={160} value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Email (optional)" htmlFor="ar-email" error={bothError}>
              <Input id="ar-email" type="email" autoComplete="off" disabled={!!code.trim()} value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field label="Employee ID (optional)" htmlFor="ar-code">
              <Input id="ar-code" autoComplete="off" disabled={!!email.trim()} maxLength={40} value={code} onChange={(e) => setCode(e.target.value)} placeholder="EMP042" />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Team" htmlFor="ar-team">
              <NativeSelect id="ar-team" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                <option value="">No team</option>
                {teams.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Job title" htmlFor="ar-title"><Input id="ar-title" maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Phone (optional)" htmlFor="ar-phone" error={phoneError}><Input id="ar-phone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} /></Field>
            <Field label="Password (optional)" htmlFor="ar-pw" error={pwError} hint="At least 8 characters. Leave empty to generate one; it is shown once.">
              <Input id="ar-pw" type="text" autoComplete="off" minLength={8} maxLength={128} value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending} disabled={invalid}>Create account</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function ImportArtistsDialog({ onClose, onDone }: { onClose: () => void; onDone: (r: ImportResult) => void }) {
  const teams = useTeams()
  const [file, setFile] = useState<File | null>(null)
  const [teamId, setTeamId] = useState("")
  const run = useAction(() => importArtistsCsv(file!, teamId ? Number(teamId) : null), { invalidate: USER_KEYS, onSuccess: onDone })
  const submit = (e: FormEvent) => { e.preventDefault(); if (file) run.mutate(undefined) }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Import artists from CSV</DialogTitle>
            <DialogDescription>
              Columns: <span className="font-mono text-xs">name</span>, and optionally <span className="font-mono text-xs">email</span> or{" "}
              <span className="font-mono text-xs">employee_id</span> (neither = automatic ID), <span className="font-mono text-xs">team, job_title, phone, password</span>.
            </DialogDescription>
          </DialogHeader>
          <Field label="CSV file" htmlFor="ai-file">
            <Input id="ai-file" type="file" accept=".csv,text/csv" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </Field>
          <Field label="Default team" htmlFor="ai-team" hint="Used for rows without a team.">
            <NativeSelect id="ai-team" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
              <option value="">No default team</option>
              {teams.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </NativeSelect>
          </Field>
          {run.error && <p className="text-sm text-destructive">{errorMessage(run.error)}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={run.isPending} disabled={!file}>Import</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
