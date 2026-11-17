import { useState } from "react"
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { BarChart3, Table2 } from "lucide-react"

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { shortDay } from "@/lib/format"
import type { DailyCount } from "@/lib/types"

/**
 * Attendance series. Stack order and hex steps were validated for the dark surface
 * (dataviz validate_palette.js: lightness band, chroma, CVD adjacency, contrast — all PASS).
 * Green and amber are deliberately never adjacent (protan ΔE 3.0 when touching).
 */
const SERIES = [
  { key: "present", label: "Present", color: "#0ca30c" },
  { key: "leave", label: "Leave", color: "#3987e5" },
  { key: "half_day", label: "Half day", color: "#c98500" },
  { key: "absent", label: "Absent", color: "#d03b3b" },
] as const

const SURFACE = "var(--card)"
const INK_MUTED = "var(--muted-foreground)"

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {SERIES.map((s) => (
        <span key={s.key} className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-[3px]" style={{ background: s.color }} />
          {s.label}
        </span>
      ))}
    </div>
  )
}

function TrendTooltip({ active, payload, label }: { active?: boolean; payload?: { payload: DailyCount }[]; label?: string }) {
  if (!active || !payload?.length || !label) return null
  const row = payload[0].payload
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-xs shadow-lg">
      <div className="mb-1.5 font-medium text-foreground">{shortDay(label)}</div>
      {SERIES.map((s) => (
        <div key={s.key} className="flex items-center justify-between gap-6 py-0.5">
          <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            <span className="size-2 rounded-[2px]" style={{ background: s.color }} />{s.label}
          </span>
          <span className="font-mono tabular text-foreground">{row[s.key]}</span>
        </div>
      ))}
    </div>
  )
}

export function AttendanceTrendChart({ data, height = 220 }: { data: DailyCount[]; height?: number }) {
  const [asTable, setAsTable] = useState(false)
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <Legend />
        <button
          type="button"
          onClick={() => setAsTable((v) => !v)}
          className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground cursor-pointer"
          aria-label={asTable ? "Show chart" : "Show as table"}
        >
          {asTable ? <BarChart3 className="size-3.5" /> : <Table2 className="size-3.5" />}
          {asTable ? "Chart" : "Table"}
        </button>
      </div>
      {asTable ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Day</TableHead>
              {SERIES.map((s) => <TableHead key={s.key} className="text-right">{s.label}</TableHead>)}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((d) => (
              <TableRow key={d.date}>
                <TableCell>{shortDay(d.date)}</TableCell>
                {SERIES.map((s) => <TableCell key={s.key} className="text-right font-mono tabular">{d[s.key]}</TableCell>)}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 4, right: 4, left: -24, bottom: 0 }} barCategoryGap="28%">
              <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="0" />
              <XAxis dataKey="date" tickFormatter={shortDay} tick={{ fill: INK_MUTED, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fill: INK_MUTED, fontSize: 11 }} axisLine={false} tickLine={false} width={40} />
              <Tooltip content={<TrendTooltip />} cursor={{ fill: "var(--accent)", opacity: 0.5 }} />
              {SERIES.map((s, i) => (
                <Bar
                  key={s.key}
                  dataKey={s.key}
                  stackId="a"
                  fill={s.color}
                  stroke={SURFACE}
                  strokeWidth={2}
                  radius={i === SERIES.length - 1 ? [4, 4, 0, 0] : 0}
                  maxBarSize={28}
                  isAnimationActive={false}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

/** Single-series magnitude list (one hue, labels carry identity — no legend needed). */
export function BarList({ items, emptyText = "No data" }: { items: { label: string; value: number }[]; emptyText?: string }) {
  const max = Math.max(1, ...items.map((i) => i.value))
  if (items.every((i) => i.value === 0)) return <p className="py-6 text-center text-xs text-muted-foreground">{emptyText}</p>
  return (
    <ul className="space-y-2.5">
      {items.map((i) => (
        <li key={i.label} className="group" title={`${i.label}: ${i.value}`}>
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="text-muted-foreground group-hover:text-foreground">{i.label}</span>
            <span className="font-mono tabular text-foreground">{i.value}</span>
          </div>
          <div className="h-1.5 rounded-full bg-muted">
            <div className="h-1.5 rounded-full bg-primary transition-[width]" style={{ width: `${(i.value / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}
