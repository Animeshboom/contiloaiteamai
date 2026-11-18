import { useState } from "react"
import { MailCheck, RefreshCw } from "lucide-react"

import { EmptyState, LoadingRows } from "@/components/common"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { NativeSelect } from "@/components/ui/form-controls"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"
import { formatDateTime, titleCase } from "@/lib/format"
import { useAction, useEmailLogs } from "@/lib/queries"
import type { EmailLogEntry, EmailStatus } from "@/lib/types"

const TONE = { pending: "neutral", sent: "green", drafted: "blue", failed: "yellow", blocked: "red" } as const

/** Admin view of every delivery attempt through the Gmail MCP integration. */
export function EmailLogCard() {
  const [status, setStatus] = useState<EmailStatus | "">("")
  const { data, isLoading } = useEmailLogs({ status: status || undefined })
  const retry = useAction((id: number) => api.post<EmailLogEntry>(`/email-logs/${id}/retry`), {
    invalidate: [["email-logs"]], success: (r) => (r.status === "sent" ? "Delivered" : `Retry result: ${r.status}`),
  })

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="flex items-center gap-2"><MailCheck className="size-4" />Email delivery log</CardTitle>
          <CardDescription>Every email sent through the Gmail MCP integration. Duplicates are prevented by idempotency keys. Blocked means the MCP server's recipient policy refused it.</CardDescription>
        </div>
        <NativeSelect className="w-36" value={status} onChange={(e) => setStatus(e.target.value as EmailStatus | "")} aria-label="Status">
          <option value="">All</option>
          {(["pending", "sent", "drafted", "failed", "blocked"] as EmailStatus[]).map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
        </NativeSelect>
      </CardHeader>
      <CardContent className="px-2">
        {isLoading ? <LoadingRows rows={3} /> : !data?.length ? <EmptyState title="No emails yet" /> : (
          <Table>
            <TableHeader>
              <TableRow><TableHead>Status</TableHead><TableHead>Email</TableHead><TableHead>To</TableHead><TableHead>Via</TableHead><TableHead>When</TableHead><TableHead /></TableRow>
            </TableHeader>
            <TableBody>
              {data.map((e) => (
                <TableRow key={e.id}>
                  <TableCell>
                    <Badge tone={TONE[e.status]} dot>{titleCase(e.status)}</Badge>
                    {e.attempts > 1 && <div className="mt-1 text-[11px] text-muted-foreground">{e.attempts} attempts</div>}
                  </TableCell>
                  <TableCell className="max-w-[15rem]">
                    <div className="truncate text-sm" title={e.subject}>{e.subject}</div>
                    <div className="font-mono text-[11px] text-muted-foreground">{e.tool_name}</div>
                    {e.error && <div className="mt-0.5 text-xs text-destructive" title={e.error}>{e.error.slice(0, 120)}</div>}
                  </TableCell>
                  <TableCell className="max-w-[9rem] truncate font-mono text-xs" title={e.recipients.join(", ")}>{e.recipients.join(", ")}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{e.provider}</TableCell>
                  <TableCell className="whitespace-nowrap text-xs">{formatDateTime(e.sent_at ?? e.last_attempt_at ?? e.created_at)}</TableCell>
                  <TableCell>
                    {e.status === "failed" && (
                      <Button variant="ghost" size="sm" onClick={() => retry.mutate(e.id)} disabled={retry.isPending}><RefreshCw />Retry</Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
