import { useEffect, useState, type FormEvent } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { LogOut, ShieldCheck } from "lucide-react"
import QRCode from "qrcode"

import { ErrorState, LoadingRows } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, Input } from "@/components/ui/form-controls"
import { api, errorMessage } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { supabaseConfirmEnroll, supabaseEnroll, supabaseHasAal2, supabaseHasFactor, supabaseVerifyCode } from "@/lib/mfa"
import { usesSupabase } from "@/lib/supabase"
import type { TokenResponse } from "@/lib/types"

/** "JBSWY3DPEHPK3PXP" -> "JBSW Y3DP EHPK 3PXP" for typing into an app by hand. */
const groupSecret = (s: string) => s.replace(/\s+/g, "").match(/.{1,4}/g)?.join(" ") ?? s

type Setup =
  | { kind: "done" }
  | { kind: "verify" }  // Supabase: factor exists, this session just needs the code
  | { kind: "enroll"; qr: string; secret: string; factorId?: string }

/** Start (or continue) two-step setup. POSTs to the API in local mode, so it must not refetch on its own:
 * every /auth/mfa/setup call makes a new secret and the QR code already scanned would stop matching. */
async function loadSetup(mfaEnabled: boolean): Promise<Setup> {
  if (usesSupabase) {
    if (await supabaseHasAal2()) return { kind: "done" }
    if (await supabaseHasFactor()) return { kind: "verify" }
    const e = await supabaseEnroll()
    return { kind: "enroll", qr: e.qrCode, secret: e.secret, factorId: e.factorId }
  }
  if (mfaEnabled) return { kind: "done" }
  const res = await api.post<{ secret: string; otpauth_uri: string }>("/auth/mfa/setup")
  const svg = await QRCode.toString(res.otpauth_uri, { type: "svg", margin: 1, width: 200 })
  return { kind: "enroll", qr: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`, secret: res.secret }
}

export default function TwoStepPage() {
  const { user, logout, setToken, refreshUser } = useAuth()
  const navigate = useNavigate()
  const [code, setCode] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const setup = useQuery({
    queryKey: ["mfa-setup"],
    queryFn: () => loadSetup(Boolean(user?.mfa_enabled)),
    staleTime: Infinity, gcTime: 0, retry: false, refetchOnWindowFocus: false, refetchOnReconnect: false,
  })
  const state = setup.data

  useEffect(() => {
    if (state?.kind === "done") void refreshUser()
  }, [state?.kind, refreshUser])

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!state || state.kind === "done") return
    setBusy(true)
    setError(null)
    try {
      let token: string
      if (!usesSupabase) {
        const res = await api.post<TokenResponse>("/auth/mfa/enable", { code: code.trim() })
        if (!res.access_token) throw new Error("Setup failed. Try again.")
        token = res.access_token
      } else if (state.kind === "enroll" && state.factorId) {
        token = await supabaseConfirmEnroll(state.factorId, code.trim())
      } else {
        token = await supabaseVerifyCode(code.trim())
      }
      setToken(token)  // the new token counts as two-step; older password-only sessions end
      await refreshUser()
      navigate("/admin", { replace: true })
    } catch (err) {
      setCode("")
      setError(errorMessage(err))  // 422 = the code didn't match
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-screen place-items-center p-4">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><ShieldCheck className="size-5 text-primary" />
            {state?.kind === "verify" ? "Enter your two-step code" : "Set up two-step login"}
          </CardTitle>
          <CardDescription>
            Admin accounts need a code from an authenticator app on your phone as well as the password.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {setup.error ? <ErrorState error={setup.error} onRetry={() => void setup.refetch()} /> : !state ? <LoadingRows rows={3} /> : state.kind === "done" ? (
            <div className="space-y-3 text-sm">
              <p>Two-step login is on for this account.</p>
              <Button asChild><Link to="/admin">Go to the admin workspace</Link></Button>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-5">
              {state.kind === "enroll" && (
                <ol className="list-decimal space-y-4 pl-5 text-sm">
                  <li>
                    Install <strong>Google Authenticator</strong>, <strong>Microsoft Authenticator</strong> or <strong>Authy</strong> on your phone.
                  </li>
                  <li>
                    In the app, add an account and scan this QR code:
                    <img src={state.qr} alt="QR code for your authenticator app" className="mt-3 size-48 rounded-md border bg-white p-2" />
                    <div className="mt-3 text-xs text-muted-foreground">Can't scan it? Choose "enter a setup key" and type:</div>
                    <div className="mt-1 select-all rounded-md border bg-muted/50 px-3 py-2 font-mono text-sm tracking-wider" data-testid="mfa-secret">
                      {groupSecret(state.secret)}
                    </div>
                  </li>
                  <li>Type the 6-digit code the app shows to finish.</li>
                </ol>
              )}
              <Field label="Enter the 6-digit code from your authenticator app" htmlFor="setup-code">
                <Input id="setup-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required
                  className="font-mono text-lg tracking-[0.4em]" placeholder="123456" value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} />
              </Field>
              {error && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
              <Button type="submit" className="w-full" loading={busy} disabled={code.length !== 6}>
                {state.kind === "verify" ? "Verify" : "Turn on two-step login"}
              </Button>
            </form>
          )}
          <div className="flex justify-end border-t pt-4">
            <Button variant="ghost" size="sm" onClick={() => { logout(); navigate("/login") }}><LogOut />Sign out</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
