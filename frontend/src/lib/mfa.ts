/**
 * Two-step login (TOTP authenticator app) for admins when the app signs in with Supabase Auth.
 *
 * In Supabase mode the API trusts the Supabase access token and requires `aal: "aal2"` in it for admin
 * data routes (otherwise 403 "mfa_required"). Supabase owns the factor, so everything here goes through
 * supabase-js `auth.mfa.*`; the StudioTrack API's own /auth/mfa/* routes are only for local sign-in.
 *
 * NOTE: this path is not covered by automated tests (it needs a live Supabase project with MFA enabled).
 * It follows the documented supabase-js v2 flow: getAuthenticatorAssuranceLevel -> listFactors ->
 * challenge -> verify (or enroll first for a new admin). After a successful verify, supabase-js stores
 * an upgraded (aal2) session; we read its access token and hand it to the API client.
 */
import { supabase } from "./supabase"
import type { User } from "./types"

/** Admin with two-step login: the password was right, now the 6-digit code is needed (auth-context completeMfa).
 * ``mfaToken`` is the short-lived (5 min) sign-in ticket in local mode; empty with Supabase (its session holds the state). */
export interface MfaChallenge { mfaRequired: true; mfaToken: string; user: User | null }
export type LoginResult = User | MfaChallenge
export const needsMfa = (r: LoginResult): r is MfaChallenge => "mfaRequired" in r

function client() {
  if (!supabase) throw new Error("Supabase sign-in is not configured")
  return supabase
}

/** True when this Supabase session is password-only but the account has a verified factor (needs the code). */
export async function supabaseNeedsCode(): Promise<boolean> {
  const { data, error } = await client().auth.mfa.getAuthenticatorAssuranceLevel()
  if (error) throw new Error(error.message)
  return data.currentLevel === "aal1" && data.nextLevel === "aal2"
}

/** True when the current session already counts as two-step (aal2). */
export async function supabaseHasAal2(): Promise<boolean> {
  const { data, error } = await client().auth.mfa.getAuthenticatorAssuranceLevel()
  if (error) throw new Error(error.message)
  return data.currentLevel === "aal2"
}

/** The verified authenticator-app factor, if this admin already set one up. */
async function verifiedTotpFactorId(): Promise<string | null> {
  const { data, error } = await client().auth.mfa.listFactors()
  if (error) throw new Error(error.message)
  return data.totp.find((f) => f.status === "verified")?.id ?? null  // `totp` only lists verified factors
}

export async function supabaseHasFactor(): Promise<boolean> {
  return (await verifiedTotpFactorId()) !== null
}

/** Challenge + verify one factor with a 6-digit code; returns the new (aal2) access token. */
async function challengeAndVerify(factorId: string, code: string): Promise<string> {
  const sb = client()
  const challenge = await sb.auth.mfa.challenge({ factorId })
  if (challenge.error) throw new Error(challenge.error.message)
  const verify = await sb.auth.mfa.verify({ factorId, challengeId: challenge.data.id, code })
  if (verify.error) throw new Error(verify.error.message.toLowerCase().includes("invalid") ? "Wrong code. Check the time on your phone and try again." : verify.error.message)
  const { data } = await sb.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new Error("Sign-in failed. Start again.")
  return token
}

/** Sign-in second step: verify the code against the admin's existing factor. */
export async function supabaseVerifyCode(code: string): Promise<string> {
  const factorId = await verifiedTotpFactorId()
  if (!factorId) throw new Error("Two-step login is not set up for this account yet")
  return challengeAndVerify(factorId, code)
}

export interface SupabaseEnrollment { factorId: string; qrCode: string; secret: string }

/** Start setup: a new TOTP factor. `qrCode` is an SVG data URL ready for <img src>. */
export async function supabaseEnroll(): Promise<SupabaseEnrollment> {
  const sb = client()
  // A half-finished earlier setup leaves an unverified factor behind; remove it so enroll doesn't conflict.
  const listed = await sb.auth.mfa.listFactors()
  if (listed.error) throw new Error(listed.error.message)
  for (const f of listed.data.all) {
    if (f.factor_type === "totp" && f.status === "unverified") await sb.auth.mfa.unenroll({ factorId: f.id })
  }
  const { data, error } = await sb.auth.mfa.enroll({ factorType: "totp" })
  if (error) throw new Error(error.message)
  return { factorId: data.id, qrCode: data.totp.qr_code, secret: data.totp.secret }
}

/** Finish setup with the first code from the app; returns the new (aal2) access token. */
export function supabaseConfirmEnroll(factorId: string, code: string): Promise<string> {
  return challengeAndVerify(factorId, code)
}
