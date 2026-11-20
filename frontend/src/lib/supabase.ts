/** Supabase Auth in the browser. Enabled only when VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY are set;
 * otherwise the app signs in against the StudioTrack API directly ("local" mode). The backend's AUTH_PROVIDER
 * must match: supabase <-> keys set here. The publishable key is public by design; never put the secret key here. */
import { createClient, type SupabaseClient } from "@supabase/supabase-js"

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined
const idDomain = (import.meta.env.VITE_LOGIN_ID_EMAIL_DOMAIN as string | undefined) || "staff.studiotrack.app"

export const supabase: SupabaseClient | null = url && key
  ? createClient(url, key, { auth: { persistSession: true, autoRefreshToken: true, storageKey: "studiotrack.auth" } })
  : null

export const usesSupabase = supabase !== null

/** People without an email sign in with an Employee ID (EMP001); it is stored as emp001@<ID domain> (same rule as the API). */
export function loginEmail(identifier: string): string {
  const id = identifier.trim()
  return id.includes("@") ? id.toLowerCase() : `${id.toLowerCase()}@${idDomain}`
}
