import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { useQueryClient } from "@tanstack/react-query"

import { api, auth } from "./api"
import { setStudioTimezone } from "./format"
import type { AppConfig, Role, User } from "./types"

interface AuthState {
  user: User | null
  config: AppConfig | null
  loading: boolean
  login: (email: string, password: string) => Promise<User>
  logout: () => void
  setToken: (token: string) => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [user, setUser] = useState<User | null>(null)
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [loading, setLoading] = useState(Boolean(auth.token))

  const logout = useCallback(() => {
    auth.set(null)
    setUser(null)
    qc.clear()
  }, [qc])

  const bootstrap = useCallback(async () => {
    const [me, cfg] = await Promise.all([api.get<User>("/auth/me"), api.get<AppConfig>("/meta/config")])
    setStudioTimezone(cfg.studio_timezone)
    setConfig(cfg)
    setUser(me)
    return me
  }, [])

  useEffect(() => {
    auth.onUnauthorized(logout)
    if (!auth.token) return
    bootstrap().catch(logout).finally(() => setLoading(false))
  }, [bootstrap, logout])

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post<{ access_token: string; user: User }>("/auth/login", { email, password })
    auth.set(res.access_token)
    return bootstrap()
  }, [bootstrap])

  const setToken = useCallback((t: string) => auth.set(t), [])

  const value = useMemo(() => ({ user, config, loading, login, logout, setToken }), [user, config, loading, login, logout, setToken])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider")
  return ctx
}

export const homeFor = (role: Role) => (role === "admin" ? "/admin" : role === "team_lead" ? "/lead" : "/artist")
