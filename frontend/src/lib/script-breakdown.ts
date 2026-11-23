/** Response of POST /screenplay/ai-breakdown(-text). */
export interface BreakdownScene {
  scene_number: number
  title: string | null
  location: string | null
  time_of_day: string | null
  characters: string[]
  duration_sec: number | null
  duration_estimated: boolean
  summary: string | null
  mood: string | null
  props: string[]
  background: string | null
  action_notes: string | null
  script_text: string | null
  description: string | null
}

export interface BreakdownEpisode {
  episode_number: number
  title: string
  scenes: BreakdownScene[]
}

export interface RuntimeCheck {
  episode_number: number
  total_sec: number
  target_sec: number
  diff_sec: number
  status: "on_target" | "short" | "long" | "unknown"
  missing_durations: number
  long_scenes: number[]
  short_scenes: number[]
  message: string
}

export interface ScriptIssue {
  severity: "high" | "medium" | "low"
  episode_number: number | null
  scene_number: number | null
  message: string
}

export interface BreakdownResult {
  ai_used: boolean
  status: string
  note: string | null
  model: string | null
  filename: string | null
  raw_text: string
  episodes: BreakdownEpisode[]
  issues: ScriptIssue[]
  runtime: RuntimeCheck[]
  scene_count: number
}

/** Scene payload accepted by the import endpoints. */
export function toImportScene(s: BreakdownScene) {
  return {
    scene_number: s.scene_number,
    title: s.title,
    description: s.description,
    duration_sec: s.duration_sec,
    characters: s.characters,
    location: s.location,
  }
}
