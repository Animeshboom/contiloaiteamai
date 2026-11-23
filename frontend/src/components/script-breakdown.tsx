import { useState } from "react"
import { AlertTriangle, ChevronDown, ChevronRight, Clock, MapPin, Sparkles, Trash2, Users } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/form-controls"
import { formatDuration } from "@/lib/format"
import type { BreakdownEpisode, BreakdownResult, BreakdownScene, RuntimeCheck } from "@/lib/script-breakdown"
import { cn } from "@/lib/utils"

const TARGET_SEC = 22 * 60

function parseMmSs(v: string): number | null {
  const t = v.trim()
  if (!t) return null
  const m = /^(\d{1,3}):([0-5]?\d)$/.exec(t)
  if (m) return Number(m[1]) * 60 + Number(m[2])
  const n = Number(t)
  return Number.isFinite(n) && n >= 0 ? n : null
}

/** green = on target, yellow = off by more than 10%, red = off by more than 25%. */
function runtimeTone(status: RuntimeCheck["status"], diff: number): "green" | "yellow" | "red" | "neutral" {
  if (status === "unknown") return "neutral"
  if (status === "on_target") return "green"
  return Math.abs(diff) > TARGET_SEC * 0.25 ? "red" : "yellow"
}

/** Live totals (they change as the user edits durations); same rule as the server: ±10% of 22:00. */
function liveRuntime(ep: BreakdownEpisode) {
  const total = ep.scenes.reduce((sum, s) => sum + (s.duration_sec ?? 0), 0)
  const diff = total - TARGET_SEC
  const status: RuntimeCheck["status"] =
    total === 0 ? "unknown" : Math.abs(diff) <= TARGET_SEC * 0.1 ? "on_target" : diff < 0 ? "short" : "long"
  return { total, diff, status }
}

function SceneRow({
  scene, flag, onChange, onRemove,
}: {
  scene: BreakdownScene
  flag: "long" | "short" | null
  onChange: (s: BreakdownScene) => void
  onRemove: () => void
}) {
  const [open, setOpen] = useState(false)
  const [dur, setDur] = useState(scene.duration_sec != null ? formatDuration(scene.duration_sec) : "")
  const notes = [
    scene.summary && ["Summary", scene.summary],
    scene.mood && ["Mood", scene.mood],
    scene.props.length > 0 && ["Props", scene.props.join(", ")],
    scene.background && ["Background", scene.background],
    scene.action_notes && ["Action", scene.action_notes],
  ].filter(Boolean) as [string, string][]

  return (
    <div className="px-2 py-1.5">
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => setOpen(!open)} className="text-muted-foreground hover:text-foreground"
          aria-label={open ? "Hide scene notes" : "Show scene notes"}>
          {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        </button>
        <span className="w-10 shrink-0 font-mono text-xs font-semibold text-primary">
          SC{String(scene.scene_number).padStart(2, "0")}
        </span>
        <Input
          value={scene.title ?? ""}
          onChange={(e) => onChange({ ...scene, title: e.target.value })}
          className="h-7 min-w-0 flex-1 text-xs"
          aria-label={`Scene ${scene.scene_number} title`}
        />
        <div className="flex shrink-0 items-center gap-1">
          <Input
            value={dur}
            onChange={(e) => setDur(e.target.value)}
            onBlur={() => {
              const sec = parseMmSs(dur)
              onChange({ ...scene, duration_sec: sec, duration_estimated: sec === scene.duration_sec && scene.duration_estimated })
              setDur(sec != null ? formatDuration(sec) : "")
            }}
            placeholder="m:ss"
            className={cn("h-7 w-16 text-center font-mono text-xs",
              flag && "border-amber-500/60", scene.duration_estimated && "italic")}
            aria-label={`Scene ${scene.scene_number} duration`}
            title={scene.duration_estimated ? "AI estimate" : "From script"}
          />
          <Button type="button" variant="ghost" size="sm" className="size-7 p-0 text-muted-foreground"
            onClick={onRemove} aria-label={`Remove scene ${scene.scene_number}`}>
            <Trash2 className="size-3.5" />
          </Button>
        </div>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 pl-[3.75rem] text-[11px] text-muted-foreground">
        {scene.location && <span className="inline-flex items-center gap-1"><MapPin className="size-3" />{scene.location}</span>}
        {scene.time_of_day && <span>{scene.time_of_day}</span>}
        {scene.characters.length > 0 && (
          <span className="inline-flex items-center gap-1"><Users className="size-3" />{scene.characters.join(", ")}</span>
        )}
        {scene.duration_estimated && <span className="italic">duration estimated</span>}
        {flag && <span className="text-amber-400">{flag === "long" ? "much longer than other scenes" : "much shorter than other scenes"}</span>}
      </div>
      {open && notes.length > 0 && (
        <dl className="mt-1.5 ml-[3.75rem] space-y-0.5 rounded border bg-muted/30 p-2 text-[11px]">
          {notes.map(([k, v]) => (
            <div key={k} className="flex gap-2"><dt className="w-20 shrink-0 font-medium text-foreground">{k}</dt><dd className="text-muted-foreground">{v}</dd></div>
          ))}
        </dl>
      )}
    </div>
  )
}

/** Editable preview of a script breakdown: runtime vs 22:00, script issues, episodes and scenes. */
export function BreakdownPreview({
  value, onChange,
}: {
  value: BreakdownResult
  onChange: (v: BreakdownResult) => void
}) {
  const setEpisode = (i: number, ep: BreakdownEpisode) =>
    onChange({ ...value, episodes: value.episodes.map((e, j) => (j === i ? ep : e)) })

  const sevTone = { high: "red", medium: "yellow", low: "neutral" } as const

  return (
    <div className="space-y-3">
      <div className={cn("flex items-start gap-2 rounded-lg border p-2.5 text-xs",
        value.ai_used ? "border-primary/30 bg-primary/5" : "border-amber-500/30 bg-amber-500/10")}>
        <Sparkles className={cn("mt-0.5 size-3.5 shrink-0", value.ai_used ? "text-primary" : "text-amber-400")} />
        <div>
          <div className="font-medium text-foreground">
            {value.ai_used ? "AI breakdown ready — check it, edit anything, then import." : "Basic breakdown (AI not used)"}
          </div>
          {value.note && <div className="text-muted-foreground">{value.note}</div>}
        </div>
      </div>

      {value.issues.length > 0 && (
        <div className="rounded-lg border p-2.5">
          <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-foreground">
            <AlertTriangle className="size-3.5 text-amber-400" />Script problems ({value.issues.length})
          </div>
          <ul className="max-h-32 space-y-1 overflow-y-auto text-xs">
            {value.issues.map((iss, i) => (
              <li key={i} className="flex items-start gap-2">
                <Badge tone={sevTone[iss.severity]}>{iss.severity}</Badge>
                <span className="text-muted-foreground">
                  {iss.episode_number != null && <span className="font-mono">EP{String(iss.episode_number).padStart(2, "0")} </span>}
                  {iss.scene_number != null && <span className="font-mono">SC{String(iss.scene_number).padStart(2, "0")} </span>}
                  {iss.message}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {value.episodes.map((ep, i) => {
        const live = liveRuntime(ep)
        const check = value.runtime.find((r) => r.episode_number === ep.episode_number)
        const flagOf = (n: number) => check?.long_scenes.includes(n) ? "long" : check?.short_scenes.includes(n) ? "short" : null
        const runtimeMsg = live.status === "unknown" ? "No durations yet"
          : live.status === "on_target" ? "on target"
          : `${formatDuration(Math.abs(live.diff))} ${live.status === "short" ? "short of" : "over"} 22:00`
        return (
          <div key={ep.episode_number} className="rounded-lg border bg-card/60">
            <div className="flex flex-wrap items-center gap-2 border-b p-2">
              <span className="font-mono text-xs font-semibold text-primary">EP{String(ep.episode_number).padStart(2, "0")}</span>
              <Input value={ep.title} onChange={(e) => setEpisode(i, { ...ep, title: e.target.value })}
                className="h-7 min-w-0 flex-1 text-xs" aria-label={`Episode ${ep.episode_number} title`} />
              <Badge tone="neutral">{ep.scenes.length} scenes</Badge>
              <Badge tone={runtimeTone(live.status, live.diff)}>
                <Clock className="mr-1 size-3" />{formatDuration(live.total)} · {runtimeMsg}
              </Badge>
            </div>
            <div className="max-h-72 divide-y overflow-y-auto">
              {ep.scenes.map((s, si) => (
                <SceneRow
                  key={`${ep.episode_number}-${s.scene_number}`}
                  scene={s}
                  flag={flagOf(s.scene_number)}
                  onChange={(ns) => setEpisode(i, { ...ep, scenes: ep.scenes.map((x, k) => (k === si ? ns : x)) })}
                  onRemove={() => setEpisode(i, { ...ep, scenes: ep.scenes.filter((_, k) => k !== si) })}
                />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
