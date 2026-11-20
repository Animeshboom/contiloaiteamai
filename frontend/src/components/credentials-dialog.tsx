import { AlertTriangle, Download, Printer } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { studioTodayNow } from "@/lib/format"
import { credentialsCsv, downloadText, printSlips } from "@/lib/credentials"
import type { Credentials } from "@/lib/types"

/**
 * One-time display of generated/reset passwords. The server never returns them again,
 * so the dialog only closes through its explicit button, not by clicking outside.
 */
export function CredentialsDialog({ title, creds, errors = [], onClose }: {
  title: string; creds: Credentials[]; errors?: { row: number; message: string }[]; onClose: () => void
}) {
  function download() {
    downloadText(credentialsCsv(creds), `logins-${studioTodayNow()}.csv`)
  }
  function print() {
    if (!printSlips(creds)) toast.error("Your browser blocked the print window. Allow pop-ups for this site and try again.")
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent wide onInteractOutside={(e) => e.preventDefault()} onEscapeKeyDown={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {creds.length > 0 && (
            <DialogDescription asChild>
              <div className="flex gap-2 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm text-warning">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                <span>These passwords are shown only once and cannot be viewed again. Download the logins or print the slips before closing.</span>
              </div>
            </DialogDescription>
          )}
        </DialogHeader>

        {creds.length > 0 && (
          <div className="max-h-[40vh] overflow-y-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow><TableHead>Name</TableHead><TableHead>Login</TableHead><TableHead>Team</TableHead><TableHead>Password</TableHead></TableRow>
              </TableHeader>
              <TableBody>
                {creds.map((c) => (
                  <TableRow key={c.user.id}>
                    <TableCell className="font-medium">{c.user.full_name}</TableCell>
                    <TableCell className="font-mono text-xs">{c.login}</TableCell>
                    <TableCell className="text-sm">{c.user.team?.name ?? "—"}</TableCell>
                    <TableCell className="font-mono text-sm select-all">{c.password}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {errors.length > 0 && (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3">
            <div className="mb-1 text-sm font-medium text-destructive">{errors.length} row{errors.length === 1 ? "" : "s"} not imported</div>
            <ul className="max-h-40 space-y-0.5 overflow-y-auto text-xs">
              {errors.map((e, i) => <li key={i}><span className="font-mono">Row {e.row}:</span> {e.message}</li>)}
            </ul>
          </div>
        )}

        <DialogFooter>
          {creds.length > 0 && (
            <>
              <Button variant="outline" onClick={download}><Download />Download logins (CSV)</Button>
              <Button variant="outline" onClick={print}><Printer />Print slips</Button>
            </>
          )}
          <Button onClick={onClose}>{creds.length ? "I've saved them — close" : "Close"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
