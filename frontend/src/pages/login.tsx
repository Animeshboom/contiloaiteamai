import { useState, type FormEvent } from "react"
import { Navigate, useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { ThemeToggle } from "@/components/theme-toggle"
import { Field, Input } from "@/components/ui/form-controls"
import { ApiError, errorMessage } from "@/lib/api"
import { homeFor, useAuth } from "@/lib/auth-context"
import { needsMfa } from "@/lib/mfa"

export default function LoginPage() {
  const { user, login, completeMfa, logout } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [locked, setLocked] = useState(false)
  const [busy, setBusy] = useState(false)
  /** Set after a correct password when the admin must also enter the authenticator code. */
  const [mfaToken, setMfaToken] = useState<string | null>(null)
  const [code, setCode] = useState("")

  if (user) return <Navigate to={homeFor(user.role)} replace />

  function showError(err: unknown) {
    setLocked(err instanceof ApiError && err.code === "account_locked")
    setError(errorMessage(err))
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await login(email.trim(), password)
      if (needsMfa(res)) {
        setPassword("")
        setCode("")
        setMfaToken(res.mfaToken)
        return
      }
      navigate(homeFor(res.role), { replace: true })
    } catch (err) {
      showError(err)
    } finally {
      setBusy(false)
    }
  }

  function backToPassword() {
    setMfaToken(null)
    setCode("")
    logout()
  }

  async function submitCode(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const u = await completeMfa(mfaToken ?? "", code.trim())
      navigate(homeFor(u.role), { replace: true })
    } catch (err) {
      setCode("")
      // 401 "Wrong code…" = try again; any other 401 means the 5-minute ticket ran out; 429 = locked.
      const wrongCode = err instanceof ApiError && err.status === 401 && /wrong code/i.test(err.message)
      if (err instanceof ApiError && (err.status === 429 || (err.status === 401 && !wrongCode))) backToPassword()
      showError(err)
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
          <div className="flex items-center gap-3">
            <div className="relative flex size-11 items-center justify-center rounded-xl border border-primary/40 bg-black/90 p-1.5 shadow-lg shadow-primary/10">
              <img src="/contiloe-emblem.svg" alt="Contiloe Logo" className="size-full object-contain" />
            </div>
            <div>
              <div className="text-lg font-bold tracking-tight text-foreground">Contiloe Entertainment</div>
              <div className="font-mono text-[11px] uppercase tracking-widest text-primary">AI StudioTrack</div>
            </div>
          </div>
          <div className="max-w-md">
            <div className="my-6 rounded-xl border border-primary/20 bg-card/40 p-5 backdrop-blur">
              <div className="flex items-center gap-4">
                <img src="/contiloe-emblem.svg" alt="Contiloe Emblem" className="size-14 rounded-lg border border-primary/30 bg-black/90 p-2 shadow-md shadow-primary/20" />
                <div>
                  <h3 className="font-bold tracking-tight text-foreground">Contiloe AI Studios</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">Empowering animation, VFX, and AI production teams.</p>
                </div>
              </div>
            </div>
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-primary">Production control</p>
            <h2 className="mt-3 text-3xl font-semibold leading-tight tracking-tight">
              Attendance, scene assignments, reviews and end-of-day reports in one place.
            </h2>
            <p className="mt-4 text-sm text-muted-foreground">
              Built for AI filmmaking teams: track every scene from assignment to approval.
            </p>
          </div>
          <div className="font-mono text-[11px] text-muted-foreground">CONTILOE ENTERTAINMENT · INTERNAL USE ONLY</div>
        </div>
      </div>

      <div className="relative flex items-center justify-center p-6">
        <ThemeToggle className="absolute right-4 top-4" />
        {mfaToken !== null ? (
          <form onSubmit={submitCode} className="w-full max-w-sm space-y-6">
            <div>
              <h1 className="text-xl font-semibold tracking-tight">Two-step login</h1>
              <p className="mt-1 text-sm text-muted-foreground">Open your authenticator app (Google Authenticator, Microsoft Authenticator or Authy).</p>
            </div>
            <Field label="Enter the 6-digit code from your authenticator app" htmlFor="mfa-code">
              <Input id="mfa-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required autoFocus
                className="font-mono text-lg tracking-[0.4em]" placeholder="123456" value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} />
            </Field>
            {error && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" loading={busy} disabled={code.length !== 6}>Verify</Button>
            <button type="button" onClick={() => { backToPassword(); setError(null) }}
              className="w-full text-center text-sm text-muted-foreground hover:text-foreground cursor-pointer">Back to sign in</button>
          </form>
        ) : (
        <form onSubmit={submit} className="w-full max-w-sm space-y-6">
          <div>
            <div className="mb-4 flex items-center gap-3 lg:hidden">
              <div className="relative flex size-10 items-center justify-center rounded-lg border border-primary/40 bg-black/90 p-1 shadow">
                <img src="/contiloe-emblem.svg" alt="Contiloe Logo" className="size-full object-contain" />
              </div>
              <div>
                <div className="text-base font-bold tracking-tight text-foreground">Contiloe Entertainment</div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-primary">StudioTrack AI</div>
              </div>
            </div>
            <h1 className="text-xl font-semibold tracking-tight">Sign in</h1>
            <p className="mt-1 text-sm text-muted-foreground">Use your studio email or the Employee ID from your admin.</p>
          </div>
          <div className="space-y-4">
            <Field label="Email or Employee ID" htmlFor="email">
              <Input id="email" autoComplete="username" autoCapitalize="none" spellCheck={false} required autoFocus
                placeholder="you@studio.com or EMP001" value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field label="Password" htmlFor="password">
              <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
          </div>
          {error && (
            <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {locked && <div className="font-medium">Account locked</div>}
              {error}
            </div>
          )}
          <Button type="submit" className="w-full" loading={busy}>Sign in</Button>

          {/* Local development only: never shown in a production build (it would publish passwords). */}
          {import.meta.env.DEV && <div className="rounded-lg border bg-card/60 p-3 text-xs">
            <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Demo Accounts (Click to autofill)</div>
            <div className="mt-2 grid grid-cols-3 gap-1.5">
              <button
                type="button"
                onClick={() => { setEmail("admin@demostudio.com"); setPassword("AdminPass123!"); }}
                className="rounded border bg-background/80 px-2 py-1 text-center font-medium transition-colors hover:bg-accent cursor-pointer"
              >
                Admin
              </button>
              <button
                type="button"
                onClick={() => { setEmail("lead@demostudio.com"); setPassword("LeadPass1234!"); }}
                className="rounded border bg-background/80 px-2 py-1 text-center font-medium transition-colors hover:bg-accent cursor-pointer"
              >
                Lead
              </button>
              <button
                type="button"
                onClick={() => { setEmail("artist@demostudio.com"); setPassword("ArtistPass12!"); }}
                className="rounded border bg-background/80 px-2 py-1 text-center font-medium transition-colors hover:bg-accent cursor-pointer"
              >
                Artist
              </button>
            </div>
          </div>}
        </form>
        )}
      </div>
    </div>
  )
}
