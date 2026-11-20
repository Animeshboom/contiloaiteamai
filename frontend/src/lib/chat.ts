/** Studio chat: query keys, cache helpers, the live-connection context and safe link parsing. */
import { createContext, useContext } from "react"
import { useQuery, type InfiniteData, type QueryClient } from "@tanstack/react-query"

import { api } from "./api"
import type { ChatChannel, ChatMessage } from "./types"

export const CHAT_PAGE = 50
export const CHAT_MAX_LENGTH = 4000
/** Own messages can be edited / deleted for this long after sending. */
export const CHAT_EDIT_WINDOW_MS = 15 * 60_000

export const chatKeys = {
  all: ["chat"] as const,
  channels: ["chat", "channels"] as const,
  unread: ["chat", "unread"] as const,
  messages: (key: string) => ["chat", "messages", key] as const,
}

/** Live connection state: while it is down, the chat page polls instead. */
export const ChatLiveContext = createContext<{ connected: boolean }>({ connected: false })
export const useChatConnected = () => useContext(ChatLiveContext).connected

export const useChatUnread = (enabled = true) =>
  useQuery({ queryKey: chatKeys.unread, queryFn: () => api.get<{ unread: number }>("/chat/unread"), enabled, refetchInterval: 30_000 })

export const useChatChannels = () => {
  const connected = useChatConnected()
  return useQuery({
    queryKey: chatKeys.channels,
    queryFn: () => api.get<ChatChannel[]>("/chat/channels"),
    refetchInterval: connected ? false : 15_000,
  })
}

export const canStillChange = (m: ChatMessage, now = Date.now()) => now - new Date(m.created_at).getTime() < CHAT_EDIT_WINDOW_MS

/* ---------- message cache (infinite query: pages[0] = newest page, each page oldest -> newest) ---------- */

type Pages = InfiniteData<ChatMessage[], number | null>

/** Add or replace one message in a loaded chat. No-op when that chat isn't loaded. */
export function upsertMessage(qc: QueryClient, m: ChatMessage) {
  qc.setQueryData<Pages>(chatKeys.messages(m.channel), (d) => {
    if (!d || d.pages.length === 0) return d
    const exists = d.pages.some((p) => p.some((x) => x.id === m.id))
    if (exists) return { ...d, pages: d.pages.map((p) => p.map((x) => (x.id === m.id ? m : x))) }
    const [newest, ...older] = d.pages
    return { ...d, pages: [[...newest, m].sort((a, b) => a.id - b.id), ...older] }
  })
}

export function markDeleted(qc: QueryClient, channel: string, id: number) {
  qc.setQueryData<Pages>(chatKeys.messages(channel), (d) =>
    d && { ...d, pages: d.pages.map((p) => p.map((x) => (x.id === id ? { ...x, deleted: true, body: null } : x))) })
}

/* ---------- links: only http(s), rendered as text + <a>, never as HTML ---------- */

export type TextPart = { text: string; href?: string }

const URL_RE = /\bhttps?:\/\/[^\s<>"'`]+/gi

/** Split text into plain parts and http(s) links. Anything else (javascript:, data:, ...) stays plain text. */
export function linkify(text: string): TextPart[] {
  const parts: TextPart[] = []
  let last = 0
  for (const match of text.matchAll(URL_RE)) {
    let raw = match[0]
    // Leave sentence punctuation outside the link; keep a ")" only when it closes a "(" in the URL.
    while (/[.,;:!?'")\]]$/.test(raw)) {
      if (raw.endsWith(")") && (raw.match(/\(/g)?.length ?? 0) >= (raw.match(/\)/g)?.length ?? 0)) break
      raw = raw.slice(0, -1)
    }
    const start = match.index ?? 0
    let href: string | null = null
    try {
      const u = new URL(raw)
      if (u.protocol === "http:" || u.protocol === "https:") href = u.href
    } catch {
      href = null
    }
    if (!href) continue
    if (start > last) parts.push({ text: text.slice(last, start) })
    parts.push({ text: raw, href })
    last = start + raw.length
  }
  if (last < text.length) parts.push({ text: text.slice(last) })
  return parts
}
