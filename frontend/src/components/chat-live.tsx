import { useEffect, useState, type ReactNode } from "react"
import { useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { ChatLiveContext, chatKeys, markDeleted, upsertMessage } from "@/lib/chat"
import type { ChatMessage } from "@/lib/types"
import { API_BASE_URL } from "@/lib/api"

/**
 * One live chat connection per tab (mounted inside the signed-in shell, so it closes on sign-out).
 * A short-lived ticket (60 s) opens the EventSource; on any error we fetch a NEW ticket and reconnect with backoff.
 * Incoming events are written straight into the React Query cache. No bell notifications for chat: badges only.
 */
export function ChatLiveProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    if (typeof EventSource === "undefined") return
    let es: EventSource | null = null
    let stopped = false
    let attempt = 0
    let timer: ReturnType<typeof setTimeout> | undefined

    const refreshCounts = () => {
      void qc.invalidateQueries({ queryKey: chatKeys.channels })
      void qc.invalidateQueries({ queryKey: chatKeys.unread })
    }
    const parse = <T,>(e: Event): T | null => {
      try { return JSON.parse((e as MessageEvent).data) as T } catch { return null }
    }
    const retry = () => {
      if (stopped) return
      const delay = Math.min(30_000, 1000 * 2 ** attempt) + Math.random() * 500
      attempt += 1
      timer = setTimeout(connect, delay)
    }

    async function connect() {
      try {
        const { ticket } = await api.post<{ ticket: string }>("/chat/stream-ticket")
        if (stopped) return
        es = new EventSource(`${API_BASE_URL}/api/v1/chat/stream?ticket=${encodeURIComponent(ticket)}`)
        es.onopen = () => {
          attempt = 0
          setConnected(true)
          void qc.invalidateQueries({ queryKey: chatKeys.all })  // catch up on anything sent while we were offline
        }
        es.addEventListener("message", (e) => {
          const m = parse<ChatMessage>(e)
          if (!m) return
          upsertMessage(qc, m)
          // A fetch of this chat already under way may not include it and would overwrite it: fetch again.
          const key = chatKeys.messages(m.channel)
          if (qc.isFetching({ queryKey: key })) void qc.invalidateQueries({ queryKey: key })
          refreshCounts()
        })
        es.addEventListener("edit", (e) => {
          const m = parse<ChatMessage>(e)
          if (m) upsertMessage(qc, m)
        })
        es.addEventListener("delete", (e) => {
          const d = parse<{ id: number; channel: string }>(e)
          if (!d) return
          markDeleted(qc, d.channel, d.id)
          void qc.invalidateQueries({ queryKey: chatKeys.channels })
        })
        es.onerror = () => {
          es?.close()
          es = null
          setConnected(false)
          retry()
        }
      } catch {
        setConnected(false)
        retry()
      }
    }

    void connect()
    return () => {
      stopped = true
      clearTimeout(timer)
      es?.close()
      setConnected(false)
    }
  }, [qc])

  return <ChatLiveContext.Provider value={{ connected }}>{children}</ChatLiveContext.Provider>
}
