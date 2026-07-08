import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { useBusiness } from '../context/BusinessContext'
import { chatApi, type ChatSession, type ChatTurn, type ChatResponse } from '../api/chat'

const SUGGESTIONS = [
  'How much revenue did I make this month?',
  'Show me my top 5 vendors by spend',
  'Are my expenses trending up?',
  'Am I profitable this quarter?',
]

export default function Chat() {
  const { selected } = useBusiness()
  const businessId = selected?.id

  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatTurn[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [pendingChart, setPendingChart] = useState<{ description: string } | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!businessId) return
    chatApi.listSessions(businessId).then(setSessions).catch(() => setSessions([]))
    setActiveId(null)
    setMessages([])
    setPendingChart(null)
  }, [businessId])

  useEffect(() => {
    if (activeId == null) {
      setMessages([])
      return
    }
    chatApi.getMessages(activeId).then(setMessages).catch(() => setMessages([]))
    setPendingChart(null)
  }, [activeId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending, pendingChart])

  // Auto-grow the textarea as the user types.
  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }, [input])

  function appendAssistantMessages(res: ChatResponse) {
    setMessages(m => {
      const next = [...m]
      if (res.answer) {
        next.push({
          id: Date.now() + 1,
          role: 'assistant',
          message: res.answer,
          created_at: new Date().toISOString(),
        })
      }
      if (res.chart_image) {
        next.push({
          id: Date.now() + 2,
          role: 'assistant',
          message: `IMAGE:${res.chart_image}`,
          created_at: new Date().toISOString(),
        })
      }
      return next
    })
  }

  async function send() {
    const text = input.trim()
    if (!text || !businessId || sending || pendingChart) return
    setInput('')
    setSending(true)

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

      if (res.status === 'pending_chart' && res.interrupt) {
        setPendingChart({ description: res.interrupt.description })
      } else {
        appendAssistantMessages(res)
      }
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

  async function confirmChart(confirmed: boolean) {
    if (!businessId || activeId == null || !pendingChart) return
    const wasPending = pendingChart
    setPendingChart(null)
    setSending(true)
    try {
      const res = await chatApi.resume(businessId, activeId, confirmed)
      appendAssistantMessages(res)
    } catch (e: any) {
      setPendingChart(wasPending)
      setMessages(m => [
        ...m,
        {
          id: Date.now() + 1,
          role: 'assistant',
          message: `Error: ${e?.message ?? 'chart request failed'}`,
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
    setPendingChart(null)
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  if (!businessId) {
    return <div className="p-6 text-gray-500">Select a business first.</div>
  }

  return (
    <div className="flex h-full">
      {/* sidebar */}
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
      <div className="flex flex-1 flex-col bg-gradient-to-b from-gray-50 to-white">
        <div className="flex-1 overflow-y-auto p-6">
          {messages.length === 0 && (
            <div className="mx-auto mt-16 max-w-xl text-center">
              <div className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-100 text-2xl">
                💬
              </div>
              <h2 className="text-lg font-semibold text-gray-800">
                Ask about {selected?.name ?? 'your business'}
              </h2>
              <p className="mt-1 text-sm text-gray-500">
                I can answer questions about revenue, expenses, vendors, and trends.
              </p>
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map(s => (
                  <button
                    key={s}
                    onClick={() => {
                      setInput(s)
                      inputRef.current?.focus()
                    }}
                    className="rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 shadow-sm transition hover:border-blue-400 hover:text-blue-600"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="mx-auto max-w-2xl space-y-6">
            {messages.map(m => (
              <MessageBubble key={m.id} turn={m} />
            ))}
            {sending && (
              <div className="flex items-start gap-3">
                <AssistantAvatar />
                <ThinkingDots />
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        {pendingChart && (
          <div className="border-t border-amber-200 bg-amber-50 px-6 py-3">
            <div className="mx-auto flex max-w-2xl items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-amber-100 text-lg">
                📊
              </div>
              <div className="flex-1 text-sm text-amber-900">
                Ready to generate: <strong>{pendingChart.description}</strong>
              </div>
              <button
                onClick={() => confirmChart(false)}
                disabled={sending}
                className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={() => confirmChart(true)}
                disabled={sending}
                className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                Approve
              </button>
            </div>
          </div>
        )}

        <div className="border-t border-gray-200 bg-white p-4">
          <div className="mx-auto flex max-w-2xl items-end gap-2 rounded-2xl border border-gray-200 bg-white px-3 py-2 shadow-sm focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100">
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
              placeholder={pendingChart ? 'Approve or cancel the chart above…' : 'Ask about your finances…'}
              disabled={!!pendingChart}
              className="min-h-[24px] flex-1 resize-none border-0 bg-transparent px-1 py-1.5 text-sm text-gray-800 placeholder:text-gray-400 focus:outline-none focus:ring-0 disabled:opacity-50"
            />
            <button
              onClick={send}
              disabled={sending || !input.trim() || !!pendingChart}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-600 text-white transition hover:bg-blue-700 disabled:opacity-40"
              aria-label="Send"
            >
              <ArrowUp />
            </button>
          </div>
          <p className="mx-auto mt-1.5 max-w-2xl text-center text-[10px] text-gray-400">
            Shift + Enter for a new line
          </p>
        </div>
      </div>
    </div>
  )
}

function MessageBubble({ turn }: { turn: ChatTurn }) {
  const isUser = turn.role === 'user'
  const isImage = !isUser && turn.message.startsWith('IMAGE:')

  if (isImage) {
    const b64 = turn.message.slice(6)
    const src = `data:image/png;base64,${b64}`
    return (
      <div className="flex items-start gap-3">
        <AssistantAvatar />
        <div className="max-w-[85%] overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <img src={src} alt="Generated chart" className="max-w-full" />
          <div className="flex items-center justify-between border-t border-gray-100 px-3 py-1.5 text-[11px] text-gray-500">
            <span>Generated chart</span>
            <a
              href={src}
              download="chart.png"
              className="text-blue-600 hover:text-blue-700"
            >
              Download
            </a>
          </div>
        </div>
      </div>
    )
  }

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl bg-blue-600 px-4 py-2 text-sm text-white shadow-sm">
          {turn.message}
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-start gap-3">
      <AssistantAvatar />
      <div className="prose prose-sm max-w-none flex-1 text-sm text-gray-800 prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-li:my-0 prose-table:text-xs">
        <ReactMarkdown>{turn.message}</ReactMarkdown>
      </div>
    </div>
  )
}

function AssistantAvatar() {
  return (
    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-500 text-xs font-semibold text-white shadow-sm">
      AI
    </div>
  )
}

function ThinkingDots() {
  return (
    <div className="flex items-center gap-1 rounded-2xl bg-gray-100 px-4 py-3">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400" />
    </div>
  )
}

function ArrowUp() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  )
}
