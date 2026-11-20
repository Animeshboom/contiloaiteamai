/** Artist-account helpers: CSV import upload, one-time credential CSV and printable login slips. */

import { ApiError, auth } from "./api"
import type { Credentials, ImportResult } from "./types"

/**
 * POST /artists/import — multipart with the CSV under "file" and an optional default team_id form field.
 * (api.upload only sends the file, so this builds the form itself with the same bearer token.)
 */
export async function importArtistsCsv(file: File, teamId?: number | null): Promise<ImportResult> {
  const form = new FormData()
  form.append("file", file)
  if (teamId) form.append("team_id", String(teamId))
  const headers: Record<string, string> = {}
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`
  let res: Response
  try {
    res = await fetch("/api/v1/artists/import", { method: "POST", headers, body: form })
  } catch {
    throw new ApiError(0, "network", "Cannot reach the StudioTrack server. Is the API running?")
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const fieldErrors = Array.isArray(data.errors) ? data.errors : []
    const message = fieldErrors.length
      ? fieldErrors.map((e: { field: string; message: string }) => `${e.field ? e.field + ": " : ""}${e.message}`).join("; ")
      : data.detail ?? `Request failed (${res.status})`
    throw new ApiError(res.status, data.error ?? "error", message, fieldErrors)
  }
  return data as ImportResult
}

const csvCell = (v: string) => (/[",\r\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)

export function credentialsCsv(creds: Credentials[], site = window.location.origin): string {
  const rows = [["Name", "Login", "Team", "Password", "Site"]]
  for (const c of creds) rows.push([c.user.full_name, c.login, c.user.team?.name ?? "", c.password, site])
  return rows.map((r) => r.map(csvCell).join(",")).join("\r\n") + "\r\n"
}

export function downloadText(text: string, filename: string, type = "text/csv;charset=utf-8") {
  const url = URL.createObjectURL(new Blob(["﻿", text], { type }))
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!)

export function slipsHtml(creds: Credentials[], site = window.location.origin): string {
  const slips = creds.map((c) => `
    <div class="slip">
      <div class="brand">StudioTrack · Sign-in details</div>
      <div class="name">${esc(c.user.full_name)}</div>
      ${c.user.team ? `<div class="team">Team: ${esc(c.user.team.name)}</div>` : ""}
      <table>
        <tr><th>Site</th><td>${esc(site)}</td></tr>
        <tr><th>Login</th><td class="mono">${esc(c.login)}</td></tr>
        <tr><th>Password</th><td class="mono">${esc(c.password)}</td></tr>
      </table>
      <div class="hint">Check in when you start and check out when you finish each day.</div>
    </div>`).join("")
  return `<!doctype html><html><head><meta charset="utf-8"><title>Login slips</title>
<style>
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 16px; color: #111; }
  .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0; }
  .slip { border: 1px dashed #888; padding: 14px 16px; break-inside: avoid; page-break-inside: avoid; }
  .brand { font-size: 10px; text-transform: uppercase; letter-spacing: .12em; color: #666; }
  .name { font-size: 16px; font-weight: 600; margin-top: 6px; }
  .team { font-size: 12px; color: #444; margin-top: 2px; }
  table { margin-top: 8px; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; font-weight: 500; color: #555; padding: 2px 12px 2px 0; }
  td { padding: 2px 0; word-break: break-all; }
  .mono { font-family: ui-monospace, Consolas, monospace; font-size: 14px; font-weight: 600; }
  .hint { margin-top: 8px; font-size: 11px; color: #666; }
  .bar { margin-bottom: 12px; }
  @media print { .bar { display: none; } body { margin: 0; } }
</style></head><body>
<div class="bar"><button onclick="window.print()">Print</button> Cut along the dashed lines.</div>
<div class="grid">${slips}</div>
<script>window.addEventListener("load", function () { window.print() })</script>
</body></html>`
}

/** Opens a printable page of cut-out slips. Returns false when the popup was blocked. */
export function printSlips(creds: Credentials[]): boolean {
  const w = window.open("", "_blank")
  if (!w) return false
  w.document.open()
  w.document.write(slipsHtml(creds))
  w.document.close()
  return true
}
