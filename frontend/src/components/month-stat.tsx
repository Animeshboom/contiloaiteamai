import { CalendarCheck } from "lucide-react"

import { useMyMonth } from "@/lib/queries"
import { cn } from "@/lib/utils"

/** "This month: 92% (23/25 days)" for the signed-in person; red when below the studio threshold. */
export function MyMonthLine() {
  const { data } = useMyMonth()
  if (!data) return null
  return (
    <div className={cn("flex items-center gap-2 rounded-lg border px-4 py-3 text-sm", data.low ? "border-destructive/40 bg-destructive/5 text-destructive" : "bg-card")}>
      <CalendarCheck className="size-4 shrink-0" />
      <span className={data.low ? "" : "text-muted-foreground"}>This month:</span>
      {data.pct == null ? <span>No working days yet</span> : (
        <span className="font-semibold">{data.pct}% <span className="font-normal">({data.present}/{data.counted_days} days)</span></span>
      )}
      {data.low && <span className="ml-auto text-xs">Attendance is low</span>}
    </div>
  )
}
