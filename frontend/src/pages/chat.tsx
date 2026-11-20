import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react"
import { useSearchParams } from "react-router-dom"
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowDown, ArrowLeft, Hash, Megaphone, MessageSquare, MoreHorizontal, Pencil, Send, ShieldCheck, Trash2 } from "lucide-react"
import { toast } from "sonner"

import { EmptyState, ErrorState, LoadingRows } from "@/components/common"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/form-controls"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/misc"
import { api, errorMessage } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import {
  CHAT_MAX_LENGTH, CHAT_PAGE, canStillChange, chatKeys, linkify, markDeleted, upsertMessage, useChatChannels, useChatConnected,
} from "@/lib/chat"
import { addDays, formatDate, formatTime, getStudioTimezone } from "@/lib/format"
import type { ChatChannel, ChatMessage } from "@/lib/types"
import { cn } from "@/lib/utils"

const KIND_ICON = { everyone: <Megaphone />, leads: <ShieldCheck />, team: <Hash /> } as const

/** Phones (< 640px) show either the list or one chat; wider screens show both and open the first chat. */
function useWide() {
  const query = "(min-width: 640px)"
  const [wide, setWide] = useState(() => (typeof window.matchMedia === "function" ? window.matchMedia(query).matches : true))
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return
    const mq = window.matchMedia(query)
    const on = () => setWide(mq.matches)
    mq.addEventListener("change", on)
    return () => mq.removeEventListener("change", on)
  }, [])
  return wide
}

export default function ChatPage() {
  const channels = useChatChannels()
  const wide = useWide()
  const [params, setParams] = useSearchParams()
  const selected = params.get("c")
  const list = channels.data ?? []
  // Desktop opens the first chat by default; phones start on the list.
  const open = list.find((c) => c.key === selected) ?? null
  const fallback = wide && !selected && list.length ? list[0] : null  // never mount a hidden chat on phones (it would mark messages read)
  const shown = open ?? fallback
  const select = (key: string | null) => setParams(key ? { c: key } : {}, { replace: !key })

  return (
    <div className="-mx-4 -my-6 lg:-mx-8 lg:-my-8">
      <div className="grid h-[calc(100dvh-3.5rem)] min-h-[420px] sm:grid-cols-[17rem_1fr]">
        <aside className={cn("min-h-0 flex-col border-r bg-sidebar", open ? "hidden sm:flex" : "flex")} aria-label="Chats">
          <div className="border-b px-4 py-3">
            <h1 className="flex items-center gap-2 text-base font-semibold"><MessageSquare className="size-4 text-primary" />Chat</h1>
            <p className="text-xs text-muted-foreground">Group chats for the studio, your team and leads.</p>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {channels.error ? <ErrorState error={channels.error} onRetry={() => void channels.refetch()} /> : channels.isLoading ? <LoadingRows rows={3} /> :
              !list.length ? <EmptyState title="No chats yet" description="You'll see your team's chat here once you're on a team." /> : (
                <ul className="space-y-0.5">
                  {list.map((c) => <ChannelItem key={c.key} c={c} active={shown?.key === c.key} onSelect={() => select(c.key)} />)}
                </ul>
              )}
          </div>
        </aside>
        <section className={cn("min-h-0 flex-col bg-background", open ? "flex" : "hidden sm:flex")}>
          {shown ? <ChatView key={shown.key} channel={shown} onBack={() => select(null)} /> : (
            <div className="grid flex-1 place-items-center p-6">
              <EmptyState title="Pick a chat" icon={<MessageSquare />} />
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

function preview(m: ChatMessage | null) {
  if (!m) return "No messages yet"
  return `${m.sender}: ${m.deleted ? "Message deleted" : m.body ?? ""}`
}

function ChannelItem({ c, active, onSelect }: { c: ChatChannel; active: boolean; onSelect: () => void }) {
  return (
    <li>
      <button type="button" onClick={onSelect} aria-current={active ? "true" : undefined}
        className={cn(
          "flex w-full items-start gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors hover:bg-accent cursor-pointer focus-visible:outline-2 focus-visible:outline-ring",
          active && "bg-accent",
        )}>
        <span className="mt-0.5 shrink-0 text-muted-foreground [&_svg]:size-4">{KIND_ICON[c.kind]}</span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className={cn("truncate text-sm", c.unread > 0 ? "font-semibold text-foreground" : "font-medium")}>{c.name}</span>
            {c.unread > 0 && (
              <span className="ml-auto shrink-0 rounded-full bg-primary px-1.5 font-mono text-[10px] font-semibold text-primary-foreground" aria-label={`${c.unread} unread`}>
                {c.unread > 99 ? "99+" : c.unread}
              </span>
            )}
          </span>
          <span className="block truncate text-xs text-muted-foreground">{preview(c.last_message)}</span>
        </span>
      </button>
    </li>
  )
}

/* ---------- one open chat ---------- */

const studioDay = (iso: string) =>
  new Intl.DateTimeFormat("en-CA", { timeZone: getStudioTimezone(), year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(iso))

function ChatView({ channel, onBack }: { channel: ChatChannel; onBack: () => void }) {
  const { user, config } = useAuth()
  const qc = useQueryClient()
  const connected = useChatConnected()
  const scroller = useRef<HTMLDivElement>(null)
  const [atBottom, setAtBottom] = useState(true)
  const [newBelow, setNewBelow] = useState(false)
  const [deleting, setDeleting] = useState<ChatMessage | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)

  const q = useInfiniteQuery({
    queryKey: chatKeys.messages(channel.key),
    queryFn: ({ pageParam }) => api.get<ChatMessage[]>(`/chat/channels/${encodeURIComponent(channel.key)}/messages`, { limit: CHAT_PAGE, before_id: pageParam ?? undefined }),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => (last.length < CHAT_PAGE ? undefined : last[0]?.id),
    refetchInterval: connected ? false : 15_000,
  })
  const messages = useMemo(() => (q.data ? [...q.data.pages].reverse().flat() : []), [q.data])
  const newest = messages.at(-1)
  const oldestId = messages[0]?.id

  // Keep the view pinned to the bottom when you're there; otherwise offer a "New messages" pill.
  const lastSeenNewest = useRef<number | undefined>(undefined)
  const prevOldest = useRef<{ id?: number; height: number }>({ height: 0 })
  useLayoutEffect(() => {
    const el = scroller.current
    if (!el) return
    if (prevOldest.current.id !== undefined && oldestId !== undefined && oldestId < prevOldest.current.id) {
      el.scrollTop += el.scrollHeight - prevOldest.current.height  // earlier messages loaded: keep your place
    } else if (newest && newest.id !== lastSeenNewest.current) {
      const first = lastSeenNewest.current === undefined
      if (first || atBottom || newest.sender_id === user?.id) el.scrollTop = el.scrollHeight
      else setNewBelow(true)
    }
    lastSeenNewest.current = newest?.id
    prevOldest.current = { id: oldestId, height: el.scrollHeight }
  }, [newest, oldestId, atBottom, user?.id])

  const onScroll = () => {
    const el = scroller.current
    if (!el) return
    const bottom = el.scrollHeight - el.scrollTop - el.clientHeight < 48
    setAtBottom(bottom)
    if (bottom) setNewBelow(false)
    prevOldest.current.height = el.scrollHeight
  }
  const toBottom = () => {
    const el = scroller.current
    if (el) el.scrollTop = el.scrollHeight
    setNewBelow(false)
    setAtBottom(true)
  }

  // Mark read (debounced) while this chat is open and the tab is visible.
  const readUpTo = useRef(0)
  useEffect(() => {
    const id = newest?.id
    if (!id) return
    let timer: ReturnType<typeof setTimeout> | undefined
    const send = () => {
      if (document.visibilityState === "hidden" || id <= readUpTo.current) return
      clearTimeout(timer)
      timer = setTimeout(() => {
        readUpTo.current = id
        api.post(`/chat/channels/${encodeURIComponent(channel.key)}/read`, { last_id: id })
          .then(() => {
            void qc.invalidateQueries({ queryKey: chatKeys.channels })
            void qc.invalidateQueries({ queryKey: chatKeys.unread })
          })
          .catch(() => { readUpTo.current = 0 })
      }, 600)
    }
    send()
    document.addEventListener("visibilitychange", send)
    return () => { clearTimeout(timer); document.removeEventListener("visibilitychange", send) }
  }, [newest?.id, channel.key, qc])

  async function confirmDelete() {
    if (!deleting) return
    setDeleteBusy(true)
    try {
      await api.del(`/chat/messages/${deleting.id}`)
      markDeleted(qc, deleting.channel, deleting.id)
      void qc.invalidateQueries({ queryKey: chatKeys.channels })
      setDeleting(null)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setDeleteBusy(false)
    }
  }

  const today = config?.studio_today
  const dayLabel = (d: string) => (d === today ? "Today" : today && d === addDays(today, -1) ? "Yesterday" : formatDate(d, true))

  return (
    <>
      <header className="flex items-center gap-2 border-b px-3 py-2.5 sm:px-4">
        <Button variant="ghost" size="icon" className="sm:hidden" onClick={onBack} aria-label="Back to chats"><ArrowLeft /></Button>
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">{channel.name}</h2>
          {!channel.can_post && <p className="text-xs text-muted-foreground">Only team leads and admins can post here</p>}
        </div>
      </header>

      <div className="relative min-h-0 flex-1">
        <div ref={scroller} onScroll={onScroll} className="h-full overflow-y-auto px-3 py-4 sm:px-5" role="log" aria-label={`${channel.name} messages`} aria-live="polite">
          {q.hasNextPage && (
            <div className="mb-3 text-center">
              <Button variant="outline" size="sm" loading={q.isFetchingNextPage} onClick={() => void q.fetchNextPage()}>Load earlier messages</Button>
            </div>
          )}
          {q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} /> : q.isLoading ? <LoadingRows rows={4} /> :
            !messages.length ? <EmptyState title="No messages yet" description={channel.can_post ? "Say hello to get things started." : undefined} /> : (
              <ol className="space-y-1">
                {messages.map((m, i) => {
                  const day = studioDay(m.created_at)
                  const prev = messages[i - 1]
                  const newDay = !prev || studioDay(prev.created_at) !== day
                  const grouped = !newDay && prev.sender_id === m.sender_id && new Date(m.created_at).getTime() - new Date(prev.created_at).getTime() < 5 * 60_000
                  return (
                    <Fragment key={m.id}>
                      {newDay && (
                        <li className="flex items-center gap-3 py-3" aria-label={dayLabel(day)}>
                          <span className="h-px flex-1 bg-border" />
                          <span className="text-xs font-medium text-muted-foreground">{dayLabel(day)}</span>
                          <span className="h-px flex-1 bg-border" />
                        </li>
                      )}
                      <MessageRow m={m} mine={m.sender_id === user?.id} isAdmin={user?.role === "admin"} grouped={grouped} onDelete={setDeleting} />
                    </Fragment>
                  )
                })}
              </ol>
            )}
        </div>
        {newBelow && (
          <button type="button" onClick={toBottom}
            className="absolute bottom-3 left-1/2 inline-flex -translate-x-1/2 items-center gap-1 rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground shadow-lg cursor-pointer">
            New messages <ArrowDown className="size-3.5" />
          </button>
        )}
      </div>

      {channel.can_post && <Composer channel={channel} onSent={toBottom} />}
      <ConfirmDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)} loading={deleteBusy} destructive
        title="Delete this message?" confirmLabel="Delete" description="Everyone in the chat will see “Message deleted” instead."
        onConfirm={() => void confirmDelete()} />
    </>
  )
}

/** Message text with http(s) links; React escapes everything else. Line breaks kept by CSS. */
function MessageText({ text }: { text: string }) {
  return (
    <>
      {linkify(text).map((p, i) => p.href ? (
        <a key={i} href={p.href} target="_blank" rel="noopener noreferrer" className="break-all font-medium underline underline-offset-2 hover:opacity-80">{p.text}</a>
      ) : <Fragment key={i}>{p.text}</Fragment>)}
    </>
  )
}

function MessageRow({ m, mine, isAdmin, grouped, onDelete }: {
  m: ChatMessage; mine: boolean; isAdmin: boolean; grouped: boolean; onDelete: (m: ChatMessage) => void
}) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState("")
  const [busy, setBusy] = useState(false)
  const [, setTick] = useState(0)  // re-check the 15-minute window when the menu opens
  const changeable = mine && !m.deleted && canStillChange(m)
  const canDelete = !m.deleted && (changeable || isAdmin)

  async function save(e?: FormEvent) {
    e?.preventDefault()
    const body = draft.trim()
    if (!body || body === m.body) { setEditing(false); return }
    setBusy(true)
    try {
      upsertMessage(qc, await api.patch<ChatMessage>(`/chat/messages/${m.id}`, { body }))
      setEditing(false)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className={cn("group flex", mine ? "justify-end" : "justify-start", !grouped && "pt-2")}>
      <div className={cn("flex max-w-[min(36rem,88%)] items-start gap-1", mine && "flex-row-reverse")}>
        <div className={cn(
          "min-w-0 rounded-lg border px-3 py-2 text-sm text-foreground",
          mine ? "border-primary/30 bg-primary/10" : "bg-card",
        )}>
          {!grouped && (
            <div className="mb-0.5 flex items-baseline gap-2 text-xs">
              <span className="font-semibold text-foreground">{mine ? "You" : m.sender}</span>
              <time dateTime={m.created_at} className="text-muted-foreground">{formatTime(m.created_at)}</time>
            </div>
          )}
          {m.deleted ? (
            <p className="italic text-muted-foreground">Message deleted</p>
          ) : editing ? (
            <form onSubmit={save} className="grid gap-2">
              <Textarea aria-label="Edit message" value={draft} maxLength={CHAT_MAX_LENGTH} rows={3} autoFocus
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") setEditing(false)
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void save() }
                }} />
              <div className="flex justify-end gap-2">
                <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
                <Button type="submit" size="sm" loading={busy}>Save</Button>
              </div>
            </form>
          ) : (
            <p className="whitespace-pre-wrap break-words">
              <MessageText text={m.body ?? ""} />
              {m.edited_at && <span className="ml-1.5 text-[11px] text-muted-foreground">(edited)</span>}
              {grouped && <time dateTime={m.created_at} className="ml-2 text-[11px] text-muted-foreground">{formatTime(m.created_at)}</time>}
            </p>
          )}
        </div>
        {(changeable || canDelete) && !editing && (
          <DropdownMenu onOpenChange={(o) => o && setTick((t) => t + 1)}>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Message actions"
                className="size-7 shrink-0 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100 sm:data-[state=open]:opacity-100">
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align={mine ? "end" : "start"}>
              {changeable && <DropdownMenuItem onSelect={() => { setDraft(m.body ?? ""); setEditing(true) }}><Pencil />Edit</DropdownMenuItem>}
              {canDelete && <DropdownMenuItem destructive onSelect={() => onDelete(m)}><Trash2 />Delete</DropdownMenuItem>}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </li>
  )
}

function Composer({ channel, onSent }: { channel: ChatChannel; onSent: () => void }) {
  const qc = useQueryClient()
  const [body, setBody] = useState("")
  const [busy, setBusy] = useState(false)
  const ref = useRef<HTMLTextAreaElement>(null)

  async function send(e?: FormEvent) {
    e?.preventDefault()
    const text = body.trim()
    if (!text || busy) return
    setBusy(true)
    try {
      const m = await api.post<ChatMessage>(`/chat/channels/${encodeURIComponent(channel.key)}/messages`, { body: text })
      upsertMessage(qc, m)
      setBody("")
      onSent()
      void qc.invalidateQueries({ queryKey: chatKeys.channels })
    } catch (err) {
      toast.error(errorMessage(err))  // 429: too many messages a minute
    } finally {
      setBusy(false)
      ref.current?.focus()
    }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void send()
    }
  }

  return (
    <form onSubmit={send} className="border-t bg-card px-3 py-3 sm:px-4">
      <div className="flex items-end gap-2">
        <Textarea ref={ref} aria-label={`Message ${channel.name}`} placeholder={`Message ${channel.name}`} rows={1}
          className="max-h-40 min-h-[40px] resize-none" maxLength={CHAT_MAX_LENGTH} value={body} readOnly={busy}
          onChange={(e) => setBody(e.target.value)} onKeyDown={onKeyDown} />
        <Button type="submit" size="icon" className="size-10 shrink-0" loading={busy} disabled={!body.trim()} aria-label="Send"><Send /></Button>
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-muted-foreground">
        <span className="hidden sm:inline">Enter to send · Shift+Enter for a new line</span>
        {body.length > CHAT_MAX_LENGTH - 500 && <span className="ml-auto">{body.length}/{CHAT_MAX_LENGTH}</span>}
      </div>
    </form>
  )
}
