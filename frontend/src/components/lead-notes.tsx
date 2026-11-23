import { useEffect, useState } from "react"
import { Link2, NotebookPen, Plus, Save, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, Input, Textarea } from "@/components/ui/form-controls"
import { api } from "@/lib/api"
import { useAction } from "@/lib/queries"
import type { LeadInput, Report } from "@/lib/types"

const EMPTY: LeadInput = { blockers: "", tomorrow_plan: "", artist_remarks: {}, links: [] }

/** Team lead's additions to the EOD report: blockers, tomorrow's plan, remarks per artist, files/links.
 *  Saving writes them into a "TEAM LEAD NOTES" block in the report text. Read-only for the admin. */
export function LeadNotesCard({ report, editable, beforeSave }: {
  report: Report; editable: boolean
  /** Save unsaved edits to the report text first, so the server-side notes block isn't lost. */
  beforeSave?: () => Promise<unknown>
}) {
  const [v, setV] = useState<LeadInput>(EMPTY)
  useEffect(() => {
    setV({ ...EMPTY, ...(report.lead_input ?? {}) })
  }, [report.id, report.lead_input])

  const save = useAction(
    async () => { await beforeSave?.(); return api.patch<Report>(`/reports/${report.id}`, {
      lead_input: {
        blockers: v.blockers?.trim() || null,
        tomorrow_plan: v.tomorrow_plan?.trim() || null,
        artist_remarks: Object.fromEntries(Object.entries(v.artist_remarks).filter(([, x]) => x.trim())),
        links: v.links.filter((l) => l.url.trim()).map((l) => ({ label: l.label?.trim() || null, url: l.url.trim() })),
      },
    }) },
    { success: "Notes saved into the report", invalidate: [["report"], ["reports"]] },
  )

  const has = !!(v.blockers || v.tomorrow_plan || Object.keys(v.artist_remarks).length || v.links.length)
  if (!editable && !has) return null

  const setLink = (i: number, patch: Partial<LeadInput["links"][number]>) =>
    setV({ ...v, links: v.links.map((l, j) => (j === i ? { ...l, ...patch } : l)) })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><NotebookPen className="size-4" />Team lead notes</CardTitle>
        <CardDescription>
          {editable ? "Added to the report under “TEAM LEAD NOTES” when you save." : "Added by the team lead."}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <Field label="Blockers / issues" htmlFor="ln-blockers">
          <Textarea id="ln-blockers" rows={3} maxLength={4000} disabled={!editable} value={v.blockers ?? ""}
            onChange={(e) => setV({ ...v, blockers: e.target.value })} placeholder="e.g. Render farm down 2 hours; need 2 more licences." />
        </Field>
        <Field label="Plan for tomorrow" htmlFor="ln-plan">
          <Textarea id="ln-plan" rows={3} maxLength={4000} disabled={!editable} value={v.tomorrow_plan ?? ""}
            onChange={(e) => setV({ ...v, tomorrow_plan: e.target.value })} placeholder="e.g. Finish SC05 lighting, start SC06 layout." />
        </Field>

        <div className="grid gap-1.5">
          <span className="text-sm font-medium">Remarks per artist</span>
          <div className="max-h-64 space-y-1.5 overflow-y-auto">
            {report.metrics.artists.map((a) => (
              <div key={a.name} className="flex items-center gap-2">
                <span className="w-36 shrink-0 truncate text-xs" title={a.name}>{a.name}</span>
                <Input className="h-8 text-xs" maxLength={500} disabled={!editable} value={v.artist_remarks[a.name] ?? ""}
                  placeholder={editable ? "Optional remark" : ""}
                  onChange={(e) => setV({ ...v, artist_remarks: { ...v.artist_remarks, [a.name]: e.target.value } })} />
              </div>
            ))}
          </div>
        </div>

        <div className="grid gap-1.5">
          <span className="flex items-center gap-1.5 text-sm font-medium"><Link2 className="size-3.5" />Files &amp; links</span>
          {v.links.map((l, i) => (
            <div key={i} className="flex items-center gap-2">
              <Input className="h-8 w-32 text-xs" maxLength={120} disabled={!editable} placeholder="Label" value={l.label ?? ""}
                onChange={(e) => setLink(i, { label: e.target.value })} />
              <Input className="h-8 text-xs" type="url" disabled={!editable} placeholder="https://drive.google.com/…" value={l.url}
                onChange={(e) => setLink(i, { url: e.target.value })} />
              {editable && (
                <Button type="button" variant="ghost" size="sm" className="size-8 p-0" aria-label="Remove link"
                  onClick={() => setV({ ...v, links: v.links.filter((_, j) => j !== i) })}><Trash2 className="size-3.5" /></Button>
              )}
            </div>
          ))}
          {editable && v.links.length < 20 && (
            <Button type="button" variant="outline" size="sm" className="w-fit"
              onClick={() => setV({ ...v, links: [...v.links, { label: "", url: "" }] })}><Plus />Add link</Button>
          )}
          {!editable && v.links.map((l, i) => (
            <a key={`a${i}`} href={l.url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline">
              {l.label || l.url} ↗
            </a>
          ))}
        </div>

        {editable && <Button loading={save.isPending} onClick={() => save.mutate(undefined)}><Save />Save notes</Button>}
      </CardContent>
    </Card>
  )
}
