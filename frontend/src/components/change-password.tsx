import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Field, Input } from "@/components/ui/form-controls"
import { api, errorMessage } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"

export function ChangePasswordDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { setToken } = useAuth()
  const [current, setCurrent] = useState("")
  const [next, setNext] = useState("")
  const [confirm, setConfirm] = useState("")
  const [busy, setBusy] = useState(false)
  const mismatch = confirm.length > 0 && next !== confirm

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (mismatch) return
    setBusy(true)
    try {
      const res = await api.post<{ access_token: string | null }>("/auth/change-password", { current_password: current, new_password: next })
      // Local sign-in returns a fresh token (other sessions are revoked); with Supabase the session continues.
      if (res.access_token) setToken(res.access_token)
      toast.success(res.access_token ? "Password changed. Other sessions have been signed out." : "Password changed.")
      setCurrent(""); setNext(""); setConfirm("")
      onOpenChange(false)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Change password</DialogTitle>
            <DialogDescription>At least 8 characters. Other signed-in sessions will be logged out.</DialogDescription>
          </DialogHeader>
          <Field label="Current password" htmlFor="cp-cur">
            <Input id="cp-cur" type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
          </Field>
          <Field label="New password" htmlFor="cp-new">
            <Input id="cp-new" type="password" autoComplete="new-password" minLength={8} required value={next} onChange={(e) => setNext(e.target.value)} />
          </Field>
          <Field label="Confirm new password" htmlFor="cp-conf" error={mismatch ? "Passwords do not match" : undefined}>
            <Input id="cp-conf" type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" loading={busy} disabled={mismatch}>Update password</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
