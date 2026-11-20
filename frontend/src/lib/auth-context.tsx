import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { useQueryClient } from "@tanstack/react-query"

import { api, auth } from "./api"
import { setStudioTimezone, studioTodayNow } from "./format"
import { supabaseNeedsCode, supabaseVerifyCode, type LoginResult } from "./mfa"
import { loginEmail, supabase } from "./supabase"
import type { AppConfig, Role, TokenResponse, User } from "./types"

interface AuthState {
  user: User | null
  config: AppConfig | null
  loading: boolean
  /** ``identifier`` is an email or an Employee ID such as EMP001. */
  login: (identifier: string, password: string) => Promise<LoginResult>
  /** Second sign-in step for admins with two-step login. */
  completeMfa: (mfaToken: string, code: string) => Promise<User>
  logout: () => void
  setToken: (token: string) => void
  /** Reload the signed-in user (and config) from the API. */
  refreshUser: () => Promise<User>
  /** The API answered 403 "mfa_required": this admin must set up (or enter) two-step login first. */
  mfaSetupRequired: boolean
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [user, setUser] = useState<User | null>(null)
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [loading, setLoading] = useState(supabase ? true : Boolean(auth.token))
  const [mfaSetupRequired, setMfaSetupRequired] = useState(false)

  const clearLocal = useCallback(() => {
    auth.set(null)
    setUser(null)
    setMfaSetupRequired(false)
    qc.clear()
  }, [qc])

  const logout = useCallback(() => {
    clearLocal()
    void supabase?.auth.signOut({ scope: "local" })
  }, [clearLocal])

  const bootstrap = useCallback(async () => {
    const [me, cfg] = await Promise.all([api.get<User>("/auth/me"), api.get<AppConfig>("/meta/config")])
    setStudioTimezone(cfg.studio_timezone)
    setConfig(cfg)
    setUser(me)
    return me
  }, [])

  useEffect(() => {
    auth.onUnauthorized(logout)
    auth.onMfaRequired(() => setMfaSetupRequired(true))
    if (supabase) {
      // supabase-js keeps the session and refreshes the access token; the API only ever sees that token.
      const { data: sub } = supabase.auth.onAuthStateChange((event, session) => {
        if (event === "SIGNED_OUT") clearLocal()
        else if (session) auth.set(session.access_token)
      })
      supabase.auth.getSession().then(({ data }) => {
        if (!data.session) return clearLocal()
        auth.set(data.session.access_token)
        return bootstrap().then(() => undefined).catch(logout)
      }).finally(() => setLoading(false))
      return () => sub.subscription.unsubscribe()
    }
    if (!auth.token) return
    bootstrap().catch(logout).finally(() => setLoading(false))
  }, [bootstrap, logout, clearLocal])

  // Keep "today" current when a tab stays open past studio midnight.
  useEffect(() => {
    if (!config) return
    const tick = () => {
      const now = studioTodayNow()
      if (now > config.studio_today) setConfig({ ...config, studio_today: now })
    }
    const id = window.setInterval(tick, 60_000)
    return () => window.clearInterval(id)
  }, [config])

  const login = useCallback(async (identifier: string, password: string): Promise<LoginResult> => {
    if (supabase) {
      const { data, error } = await supabase.auth.signInWithPassword({ email: loginEmail(identifier), password })
      if (error || !data.session) {
        throw new Error(error?.message === "Invalid login credentials" ? "Wrong ID/email or password" : error?.message ?? "Sign-in failed")
      }
      auth.set(data.session.access_token)
      const me = await api.post<User>("/auth/session")  // artists: this device becomes the only signed-in one
      if (me.role === "artist") void supabase.auth.signOut({ scope: "others" })
      // Admin with an authenticator factor: Supabase needs the code before the token counts as two-step (aal2).
      if (me.role === "admin" && await supabaseNeedsCode()) return { mfaRequired: true, mfaToken: "", user: me }
      setMfaSetupRequired(false)
      return bootstrap()
    }
    const res = await api.post<TokenResponse>("/auth/login", { email: identifier, password })
    if (res.mfa_required || !res.access_token) {
      return { mfaRequired: true, mfaToken: res.mfa_token ?? "", user: res.user }
    }
    auth.set(res.access_token)
    setMfaSetupRequired(false)
    return bootstrap()
  }, [bootstrap])

  const completeMfa = useCallback(async (mfaToken: string, code: string) => {
    if (supabase) {
      auth.set(await supabaseVerifyCode(code))
    } else {
      const res = await api.post<TokenResponse>("/auth/login/mfa", { mfa_token: mfaToken, code })
      if (!res.access_token) throw new Error("Sign-in failed. Start again.")
      auth.set(res.access_token)
    }
    setMfaSetupRequired(false)
    return bootstrap()
  }, [bootstrap])

  const setToken = useCallback((t: string) => auth.set(t), [])

  const refreshUser = useCallback(async () => {
    const me = await bootstrap()
    setMfaSetupRequired(false)
    // Re-run what failed with "mfa_required"; leave the rest alone (re-running the two-step setup would make a new secret).
    await qc.invalidateQueries({ predicate: (q) => q.state.status === "error" })
    return me
  }, [bootstrap, qc])

  const value = useMemo(
    () => ({ user, config, loading, login, completeMfa, logout, setToken, refreshUser, mfaSetupRequired }),
    [user, config, loading, login, completeMfa, logout, setToken, refreshUser, mfaSetupRequired],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider")
  return ctx
}

/** A selected day that starts at studio "today" and moves forward with it at midnight, unless the user picked another day. */
export function useStudioDay() {
  const { config } = useAuth()
  const today = config?.studio_today ?? ""
  const [day, setDay] = useState(today)
  const [seenToday, setSeenToday] = useState(today)
  if (seenToday !== today) {
    setSeenToday(today)
    if (!day || day === seenToday) setDay(today)
  }
  return [day, setDay, today] as const
}

export const homeFor = (role: Role) => (role === "admin" ? "/admin" : role === "team_lead" ? "/lead" : "/artist")
