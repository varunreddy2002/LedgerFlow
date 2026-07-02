import { useEffect, useRef, useState } from 'react'
import { useBusiness } from '../context/BusinessContext'
import { chatApi, type ChatSession, type ChatTurn } from '../api/chat'

export default function Chat() {
  const { selected } = useBusiness()
  const businessId = selected?.id

  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatTurn[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  // load sessions when the business changes
  useEffect(() => {
    if (!businessId) return
    chatApi.listSessions(businessId).then(setSessions).catch(() => setSessions([]))
    setActiveId(null)
    setMessages([])
  }, [businessId])

  // load messages when the active session changes
  useEffect(() => {
    if (activeId == null) {
      setMessages([])
      return
    }
    chatApi.getMessages(activeId).then(setMessages).catch(() => setMessages([]))
  }, [activeId])

  // keep the thread scrolled to the newest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  async function send() {
    const text = input.trim()
    if (!text || !businessId || sending) return
    setInput('')
    setSending(true)

    // optimistic user bubble
    setMessages(m => [
      ...m,
      { id: Date.now(), role: 'user', message: text, created_at: new Date().toISOString() },
    ])

    try {
      const res = await chatApi.send(businessId, text, activeId)
      if (activeId == null) {
        setActiveId(res.session_id)
        chatApi.listSessions(businessId).then(setSessions).catch(() => {})
      }
      setMessages(m => [
        ...m,
        { id: Date.now() + 1, role: 'assistant', message: res.answer, created_at: new Date().toISOString() },
      ])
    } catch (e: any) {
      setMessages(m => [
        ...m,
        {
          id: Date.now() + 1,
          role: 'assistant',
          message: `Error: ${e?.message ?? 'request failed'}`,
          created_at: new Date().toISOString(),
        },
      ])
    } finally {
      setSending(false)
    }
  }

  function newChat() {
    setActiveId(null)
    setMessages([])
    setInput('')
  }

  if (!businessId) {
    return <div className="p-6 text-gray-500">Select a business first.</div>
  }

  return (
    <div className="flex h-full">
      {/* session list */}
      <div className="flex w-56 shrink-0 flex-col border-r border-gray-200 bg-white">
        <div className="p-3">
          <button
            onClick={newChat}
            className="w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            + New chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-2">
          {sessions.map(s => (
            <button
              key={s.id}
              onClick={() => setActiveId(s.id)}
              className={`mb-0.5 block w-full truncate rounded-md px-3 py-2 text-left text-sm ${
                activeId === s.id ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              {s.title || `Session ${s.id}`}
            </button>
          ))}
        </div>
      </div>

      {/* thread */}
      <div className="flex flex-1 flex-col">
        <div className="flex-1 overflow-y-auto p-6">
          {messages.length === 0 && (
            <div className="mt-24 text-center text-sm text-gray-400">
              Ask about your finances — e.g. “What was my net income in June 2026?”
            </div>
          )}
          <div className="mx-auto max-w-2xl space-y-4">
            {messages.map(m => (
              <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${
                    m.role === 'user' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-900'
                  }`}
                >
                  {m.message}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <div className="rounded-2xl bg-gray-100 px-4 py-2 text-sm text-gray-500">Thinking…</div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        {/* input */}
        <div className="border-t border-gray-200 bg-white p-4">
          <div className="mx-auto flex max-w-2xl gap-2">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') send()
              }}
              placeholder="Ask a question..."
              className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={send}
              disabled={sending || !input.trim()}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
