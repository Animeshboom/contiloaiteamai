import { useState, type FormEvent } from "react"
import { Plus, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/form-controls"
import { api } from "@/lib/api"
import { useAction, useFeedbackPhrases } from "@/lib/queries"
import type { FeedbackPhrase } from "@/lib/types"

/** Admin: the studio's quick feedback phrases that leads click to add to a review. */
export function FeedbackPhrasesCard() {
  const { data } = useFeedbackPhrases()
  const [text, setText] = useState("")
  const add = useAction(() => api.post<FeedbackPhrase>("/feedback-phrases", { text: text.trim() }), {
    success: "Phrase added", invalidate: [["feedback-phrases"]], onSuccess: () => setText(""),
  })
  const remove = useAction((id: number) => api.del(`/feedback-phrases/${id}`), { success: "Phrase removed", invalidate: [["feedback-phrases"]] })
  const submit = (e: FormEvent) => { e.preventDefault(); if (text.trim()) add.mutate(undefined) }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Feedback phrases</CardTitle>
        <CardDescription>Quick phrases leads can click to add to review feedback.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!data?.length ? <p className="text-sm text-muted-foreground">No phrases yet.</p> : (
          <ul className="flex flex-wrap gap-1.5">
            {data.map((p) => (
              <li key={p.id} className="flex items-center gap-1 rounded-full border bg-background/60 py-0.5 pl-2.5 pr-1 text-xs">
                {p.text}
                <button type="button" className="rounded-full p-0.5 text-muted-foreground hover:text-destructive cursor-pointer"
                  disabled={remove.isPending} onClick={() => remove.mutate(p.id)} aria-label={`Remove "${p.text}"`}><X className="size-3" /></button>
              </li>
            ))}
          </ul>
        )}
        <form onSubmit={submit} className="flex gap-2">
          <Input value={text} maxLength={200} onChange={(e) => setText(e.target.value)} placeholder="e.g. Great timing on the camera move." aria-label="New phrase" />
          <Button type="submit" variant="outline" loading={add.isPending} disabled={!text.trim()}><Plus />Add</Button>
        </form>
      </CardContent>
    </Card>
  )
}
