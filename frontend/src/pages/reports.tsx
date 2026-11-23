import { useEffect, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { FileText, Sparkles } from "lucide-react"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common"
import { ReportMetricsView } from "@/components/report-metrics"
import { ReportStatusBadge } from "@/components/report-status"
import { TeamReportStatusCard } from "@/components/team-report-status"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox, Field, Input, NativeSelect } from "@/components/ui/form-controls"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"
import { useAuth, useStudioDay } from "@/lib/auth-context"
import { formatDate, formatDateTime } from "@/lib/format"
import { useAction, useProject, useProjects, useReportMetrics, useReports, useTeams, useUsers } from "@/lib/queries"
import type { Report } from "@/lib/types"

export default function ReportsPage() {
  const { user, config } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const base = user?.role === "admin" ? "/admin/reports" : "/lead/reports"
  const isAdmin = user?.role === "admin"
  const emailOn = config?.email_enabled !== false

  // Deep links from notifications (?open=ID)
  const openId = params.get("open")
  useEffect(() => { if (openId) navigate(`${base}/${openId}`, { replace: true }) }, [openId, base, navigate])

  const [day, setDay, today] = useStudioDay()
  const [projectId, setProjectId] = useState("")
  const [episodeId, setEpisodeId] = useState("")
  const [artistId, setArtistId] = useState("")
  const [teamId, setTeamId] = useState("")
  const [useAi, setUseAi] = useState(true)

  const projects = useProjects()
  const project = useProject(projectId ? Number(projectId) : undefined)
  const artists = useUsers({ role: "artist" })
  const teams = useTeams()
  const filters = {
    report_date: day || undefined, project_id: projectId || undefined, episode_id: episodeId || undefined,
    artist_id: artistId || undefined, team_id: isAdmin ? teamId || undefined : undefined,
  }
  const metrics = useReportMetrics(filters)
  const history = useReports()

  const generate = useAction(
    () => api.post<Report>("/reports", {
      report_date: day, project_id: projectId ? Number(projectId) : null, episode_id: episodeId ? Number(episodeId) : null,
      artist_id: artistId ? Number(artistId) : null, team_id: isAdmin && teamId ? Number(teamId) : null, use_ai: useAi && !!config?.ai_enabled,
    }),
    { success: config?.email_enabled === false ? "Report drafted — review it, then send it to the admin" : "Report drafted — review it before sending", invalidate: [["reports"], ["notifications"]], onSuccess: (r) => navigate(`${base}/${r.id}`) },
  )

  return (
    <>
      <PageHeader title={isAdmin ? "Reports" : "EOD reports"} description="Consolidated end-of-day production report. Figures come from the records; the AI only drafts the wording." />

      {isAdmin && <TeamReportStatusCard day={day} />}

      <Card className="mb-6">
        <CardHeader><CardTitle>Report scope</CardTitle></CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6 lg:items-end">
            <Field label="Date" htmlFor="r-date"><Input id="r-date" type="date" max={today} value={day} onChange={(e) => setDay(e.target.value)} /></Field>
            {isAdmin && (
              <Field label="Team" htmlFor="r-team">
                <NativeSelect id="r-team" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                  <option value="">All teams</option>
                  {teams.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </NativeSelect>
              </Field>
            )}
            <Field label="Project" htmlFor="r-proj">
              <NativeSelect id="r-proj" value={projectId} onChange={(e) => { setProjectId(e.target.value); setEpisodeId("") }}>
                <option value="">All projects</option>
                {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.title}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Episode" htmlFor="r-ep">
              <NativeSelect id="r-ep" value={episodeId} disabled={!projectId} onChange={(e) => setEpisodeId(e.target.value)}>
                <option value="">All episodes</option>
                {project.data?.episodes.map((e) => <option key={e.id} value={e.id}>EP{String(e.episode_number).padStart(2, "0")} {e.title}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Artist" htmlFor="r-artist">
              <NativeSelect id="r-artist" value={artistId} onChange={(e) => setArtistId(e.target.value)}>
                <option value="">All artists</option>
                {artists.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
              </NativeSelect>
            </Field>
            <div className="flex flex-col gap-2 lg:col-span-1">
              <label className="flex items-center gap-2 text-xs text-muted-foreground" title={config?.ai_enabled ? "" : "An admin can add an AI key in Settings → AI provider"}>
                <Checkbox checked={useAi && !!config?.ai_enabled} disabled={!config?.ai_enabled} onCheckedChange={(c) => setUseAi(!!c)} />
                {config?.ai_enabled ? `${config.ai_provider ?? "AI"} narrative` : "Template narrative (no API key)"}
              </label>
              <Button onClick={() => generate.mutate(undefined)} loading={generate.isPending} disabled={!day}><Sparkles />Generate report</Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold">{day ? formatDate(day, true) : "—"} {metrics.data && <span className="font-normal text-muted-foreground">· {metrics.data.as_of}</span>}</h2>
        <span className="text-xs text-muted-foreground">Live figures · nothing is saved until you generate</span>
      </div>
      {metrics.error ? <ErrorState error={metrics.error} onRetry={metrics.refetch} /> : !metrics.data ? <LoadingRows /> : <ReportMetricsView m={metrics.data} />}

      <Card className="mt-8">
        <CardHeader><CardTitle>Report history</CardTitle><CardDescription>Every generated report is kept, including drafts and failed sends.</CardDescription></CardHeader>
        <CardContent className="px-2">
          {history.isLoading ? <LoadingRows rows={3} /> : !history.data?.length ? <EmptyState icon={<FileText />} title="No reports yet" description="Generate today's report above." /> : (
            <Table>
              <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Status</TableHead><TableHead>Subject</TableHead>{emailOn && <TableHead>Recipients</TableHead>}<TableHead>Sent</TableHead></TableRow></TableHeader>
              <TableBody>
                {history.data.map((r) => (
                  <TableRow key={r.id} className="cursor-pointer" onClick={() => navigate(`${base}/${r.id}`)}>
                    <TableCell className="whitespace-nowrap">{formatDate(r.report_date)}<div className="font-mono text-[11px] text-muted-foreground">#{r.id}</div></TableCell>
                    <TableCell>{emailOn || r.status !== "draft" ? <ReportStatusBadge status={r.status} /> : r.submitted_at ? <span className="text-xs text-success">Sent to admin</span> : <ReportStatusBadge status={r.status} />}</TableCell>
                    <TableCell className="max-w-xs truncate text-sm">{r.subject}</TableCell>
                    {emailOn && <TableCell className="max-w-[12rem] truncate font-mono text-xs">{r.recipients.join(", ")}</TableCell>}
                    <TableCell className="whitespace-nowrap text-xs">
                      {r.submitted_at ? <>To admin {formatDateTime(r.submitted_at)}{r.issues && <div className="text-warning">Has issues</div>}</>
                        : r.sent_at ? <>{formatDateTime(r.sent_at)}<div className="text-muted-foreground">by {r.sent_by_name}</div></> : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  )
}
