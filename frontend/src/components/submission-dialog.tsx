import { useState } from "react"
import { Link } from "react-router-dom"
import { RotateCcw } from "lucide-react"

import { LoadingRows } from "@/components/common"
import { SubmissionBody } from "@/components/submission-view"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useAuth } from "@/lib/auth-context"
import { useSubmission } from "@/lib/queries"

/** Opens a submission by id; can hop to the previous revision in place. */
export function SubmissionDialog({ id, onClose }: { id: number; onClose: () => void }) {
  const { user } = useAuth()
  const [current, setCurrent] = useState(id)
  const { data } = useSubmission(current)
  const isArtist = user?.role === "artist"

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent wide>
        <DialogHeader>
          <div className="font-mono text-[11px] text-muted-foreground">
            Submission #{current}{data && ` · ${data.project_code}${data.episode_number != null ? ` · EP${String(data.episode_number).padStart(2, "0")}` : ""}`}
          </div>
          <DialogTitle className="pr-8">{data?.assignment_title ?? "Loading…"}</DialogTitle>
          <DialogDescription className="sr-only">Submission details and review history</DialogDescription>
        </DialogHeader>
        {!data ? <LoadingRows rows={4} /> : (
          <>
            <SubmissionBody sub={data} showArtist={!isArtist} onOpenSubmission={setCurrent} />
            {isArtist && data.status === "rejected" && (
              <div className="flex justify-end border-t pt-4">
                <Button asChild><Link to={`/artist/submit?assignment=${data.assignment_id}`} onClick={onClose}><RotateCcw />Revise &amp; resubmit</Link></Button>
              </div>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
