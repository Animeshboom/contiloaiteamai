import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ChatLiveProvider } from "@/components/chat-live"
import { linkify } from "@/lib/chat"
import type { ChatChannel, ChatMessage, Role } from "@/lib/types"
import ChatPage from "./chat"

const auth = vi.hoisted(() => ({ role: "team_lead" as Role, id: 2 }))
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ user: { id: auth.id, role: auth.role, full_name: "Priya Raman" }, config: { studio_today: "2026-11-20" } }),
}))

/** Minimal EventSource stand-in: tests push events with emit(). */
class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  closed = false
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {}
  constructor(url: string) { this.url = url; FakeEventSource.instances.push(this) }
  addEventListener(type: string, cb: (e: MessageEvent) => void) { (this.listeners[type] ??= []).push(cb) }
  close() { this.closed = true }
  emit(type: string, data: unknown) { this.listeners[type]?.forEach((cb) => cb(new MessageEvent(type, { data: JSON.stringify(data) }))) }
}

const msg = (over: Partial<ChatMessage>): ChatMessage => ({
  id: 1, channel: "everyone", sender_id: 1, sender: "Admin One", body: "Hello", created_at: "2026-11-20T05:00:00Z", edited_at: null, deleted: false, ...over,
})
const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }))

let channels: ChatChannel[]
let history: ChatMessage[]

function renderChat() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/lead/chat"]}>
        <ChatLiveProvider><ChatPage /></ChatLiveProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("ChatPage", () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal("EventSource", FakeEventSource)
    vi.stubGlobal("fetch", fetchMock)
    auth.role = "team_lead"
    auth.id = 2
    channels = [
      { key: "everyone", name: "Everyone", kind: "everyone", can_post: true, unread: 0, last_message: msg({}) },
      { key: "leads", name: "Leads & Admin", kind: "leads", can_post: true, unread: 0, last_message: null },
      { key: "team:1", name: "Animation Unit", kind: "team", can_post: true, unread: 3, last_message: msg({ id: 9, channel: "team:1", sender: "Asha Rao", body: "Render done" }) },
    ]
    history = [msg({})]
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET"
      if (url === "/api/v1/chat/channels") return json(200, channels)
      if (url === "/api/v1/chat/unread") return json(200, { unread: 3 })
      if (url === "/api/v1/chat/stream-ticket") return json(200, { ticket: "t1" })
      if (url.endsWith("/read")) return Promise.resolve(new Response(null, { status: 204 }))
      if (url.startsWith("/api/v1/chat/channels/everyone/messages") && method === "POST") {
        const body = JSON.parse(String(init?.body)).body
        return json(201, msg({ id: 50, sender_id: 2, sender: "Priya Raman", body }))
      }
      if (url.startsWith("/api/v1/chat/channels/everyone/messages")) return json(200, history)
      return json(404, {})
    })
  })
  afterEach(() => { fetchMock.mockReset(); vi.unstubAllGlobals() })

  it("lists the chats with unread badges and a last-message preview", async () => {
    renderChat()
    const list = await screen.findByRole("complementary", { name: "Chats" })
    expect(await within(list).findByText("Animation Unit")).toBeInTheDocument()
    expect(within(list).getByText("Leads & Admin")).toBeInTheDocument()
    expect(within(list).getByLabelText("3 unread")).toHaveTextContent("3")
    expect(within(list).getByText("Asha Rao: Render done")).toBeInTheDocument()
  })

  it("sends a message with Enter and shows it", async () => {
    renderChat()
    const box = await screen.findByLabelText("Message Everyone")
    await userEvent.type(box, "Dailies at 4{Enter}")

    await waitFor(() => expect(fetchMock.mock.calls.some(([u, i]) => u === "/api/v1/chat/channels/everyone/messages" && i?.method === "POST")).toBe(true))
    const [, init] = fetchMock.mock.calls.find(([u, i]) => u === "/api/v1/chat/channels/everyone/messages" && i?.method === "POST")!
    expect(JSON.parse(String(init.body))).toEqual({ body: "Dailies at 4" })
    expect(await screen.findByText("Dailies at 4")).toBeInTheDocument()
    expect(box).toHaveValue("")
  })

  it("artists can read Everyone but not post there", async () => {
    auth.role = "artist"
    auth.id = 5
    channels[0] = { ...channels[0], can_post: false }
    renderChat()
    expect(await screen.findByText("Only team leads and admins can post here")).toBeInTheDocument()
    expect(await screen.findByText("Hello")).toBeInTheDocument()
    expect(screen.queryByLabelText("Message Everyone")).not.toBeInTheDocument()
  })

  it("turns http(s) URLs into safe links and leaves javascript: as text", async () => {
    history = [msg({ body: "Call: https://meet.google.com/abc-defg-hij.\nNot this: javascript:alert(1)" })]
    renderChat()
    const link = await screen.findByRole("link", { name: "https://meet.google.com/abc-defg-hij" })
    expect(link).toHaveAttribute("href", "https://meet.google.com/abc-defg-hij")
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
    expect(screen.getAllByRole("link")).toHaveLength(1)
    expect(screen.getByText(/javascript:alert\(1\)/)).toBeInTheDocument()

    expect(linkify("javascript:alert(1) data:text/html,x")).toEqual([{ text: "javascript:alert(1) data:text/html,x" }])
    expect(linkify("see (https://zoom.us/j/1)!")).toEqual([{ text: "see (" }, { text: "https://zoom.us/j/1", href: "https://zoom.us/j/1" }, { text: ")!" }])
  })

  it("shows a message that arrives on the live stream", async () => {
    renderChat()
    expect(await screen.findByText("Hello")).toBeInTheDocument()
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    const es = FakeEventSource.instances[0]
    expect(es.url).toBe("/api/v1/chat/stream?ticket=t1")

    // (no onopen here: its catch-up refetch would load the message anyway; this checks the event itself)
    act(() => es.emit("message", msg({ id: 77, sender_id: 1, sender: "Admin One", body: "Wrap party Friday" })))
    expect(await screen.findByText("Wrap party Friday")).toBeInTheDocument()

    act(() => es.emit("delete", { id: 77, channel: "everyone" }))
    expect(await screen.findByText("Message deleted")).toBeInTheDocument()
  })
})
