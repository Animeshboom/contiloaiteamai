import { useState, type FormEvent } from "react"
import { Navigate, useNavigate } from "react-router-dom"
import { Clapperboard } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Field, Input } from "@/components/ui/form-controls"
import { errorMessage } from "@/lib/api"
import { homeFor, useAuth } from "@/lib/auth-context"

/** Seeded demo accounts (see README). Only shown in development builds. */
const DEMO = [
  { label: "Admin", email: "admin@studiotrack.demo", password: "Admin@12345" },
  { label: "Team Lead", email: "lead.anim@studiotrack.demo", password: "Lead@12345" },
  { label: "Artist", email: "artist.arjun@studiotrack.demo", password: "Artist@12345" },
]

export default function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={homeFor(user.role)} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const u = await login(email, password)
      navigate(homeFor(u.role), { replace: true })
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <div className="relative hidden overflow-hidden border-r bg-sidebar lg:block">
        {/* film-strip motif */}
        <div className="absolute inset-y-0 left-10 flex w-10 flex-col gap-3 py-6 opacity-30">
          {Array.from({ length: 30 }).map((_, i) => <div key={i} className="h-5 rounded-sm border border-muted-foreground/40" />)}
        </div>
        <div className="relative flex h-full flex-col justify-between p-12 pl-28">
          <div className="flex items-center gap-2.5">
            <div className="grid size-9 place-items-center rounded-md border border-primary/40 bg-primary/10 text-primary"><Clapperboard className="size-5" /></div>
            <span className="text-lg font-semibold tracking-tight">StudioTrack AI</span>
          </div>
          <div className="max-w-md">
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-primary">Production control</p>
            <h2 className="mt-3 text-3xl font-semibold leading-tight tracking-tight">
              Attendance, scene assignments, reviews and end-of-day reports in one place.
            </h2>
            <p className="mt-4 text-sm text-muted-foreground">
              Built for AI filmmaking teams: track every scene from assignment to approval.
            </p>
          </div>
          <div className="font-mono text-[11px] text-muted-foreground">INTERNAL · AUTHORIZED PERSONNEL</div>
        </div>
      </div>

      <div className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-6">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Sign in</h1>
            <p className="mt-1 text-sm text-muted-foreground">Use your studio account.</p>
          </div>
          <div className="space-y-4">
            <Field label="Email" htmlFor="email">
              <Input id="email" type="email" autoComplete="username" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field label="Password" htmlFor="password">
              <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
          </div>
          {error && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" loading={busy}>Sign in</Button>

          {import.meta.env.DEV && (
            <div className="rounded-lg border border-dashed p-3">
              <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Demo accounts (dev only)</p>
              <div className="grid grid-cols-3 gap-2">
                {DEMO.map((d) => (
                  <Button key={d.email} type="button" variant="outline" size="sm" onClick={() => { setEmail(d.email); setPassword(d.password) }}>
                    {d.label}
                  </Button>
                ))}
              </div>
            </div>
          )}
        </form>
      </div>
    </div>
  )
}
