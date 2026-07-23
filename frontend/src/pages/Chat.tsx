import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { useBusiness } from '../context/BusinessContext'
import { chatApi, type ChatSession, type ChatTurn, type ChatInterrupt, type StreamEvent } from '../api/chat'

const SUGGESTIONS = [
  'How much revenue did I make this month?',
  'Show me my top 5 vendors by spend',
  'Are my expenses trending up?',
  'Am I profitable this quarter?',
]

interface Streaming {
  text: string
  trace: string[]
}

export default function Chat() {
  const { selected } = useBusiness()
  const businessId = selected?.id

  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatTurn[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [pending, setPending] = useState<ChatInterrupt | null>(null)
  const [streaming, setStreaming] = useState<Streaming | null>(null)
  // authoritative accumulator for the in-flight stream (avoids stale closures)
  const streamRef = useRef<Streaming>({ text: '', trace: [] })
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!businessId) return
    chatApi.listSessions(businessId).then(setSessions).catch(() => setSessions([]))
    setActiveId(null)
    setMessages([])
    setPending(null)
    setStreaming(null)
  }, [businessId])

  useEffect(() => {
    if (activeId == null) {
      setMessages([])
      return
    }
    chatApi.getMessages(activeId).then(setMessages).catch(() => setMessages([]))
    setPending(null)
  }, [activeId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streaming, pending])

  // Auto-grow the textarea as the user types.
  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }, [input])

  function assistantTurn(message: string): ChatTurn {
    return { id: Date.now() + Math.random(), role: 'assistant', message, created_at: new Date().toISOString() }
  }

  function startStream() {
    streamRef.current = { text: '', trace: [] }
    setStreaming({ text: '', trace: [] })
  }

  // Move the accumulated stream text into the permanent thread, then stop streaming.
  function finalizeStream(finalText?: string, chartImage?: string | null) {
    const text = (finalText ?? streamRef.current.text).trim()
    setMessages(m => {
      const next = [...m]
      if (text) next.push(assistantTurn(text))
      if (chartImage) next.push(assistantTurn(`IMAGE:${chartImage}`))
      return next
    })
    setStreaming(null)
  }

  function handleEvent(ev: StreamEvent) {
    switch (ev.type) {
      case 'session':
        if (activeId == null && ev.session_id != null) {
          setActiveId(ev.session_id)
          if (businessId) chatApi.listSessions(businessId).then(setSessions).catch(() => {})
        }
        break
      case 'tool_call': {
        const label = traceLabel(ev)
        if (label) {
          streamRef.current.trace = [...streamRef.current.trace, label]
          setStreaming({ ...streamRef.current })
        }
        break
      }
      case 'token':
        streamRef.current.text += ev.text ?? ''
        setStreaming({ ...streamRef.current })
        break
      case 'interrupt':
        finalizeStream()
        setPending(ev.payload ?? null)
        break
      case 'done':
        finalizeStream(ev.answer, ev.chart_image)
        break
      case 'error':
        finalizeStream()
        setMessages(m => [...m, assistantTurn(`Error: ${ev.message ?? 'stream failed'}`)])
        break
    }
  }

  async function send() {
    const text = input.trim()
    if (!text || !businessId || sending || pending) return
    setInput('')
    setSending(true)
    setMessages(m => [
      ...m,
      { id: Date.now(), role: 'user', message: text, created_at: new Date().toISOString() },
    ])
    startStream()

    try {
      await chatApi.streamSend(businessId, text, activeId, handleEvent)
    } catch (e: any) {
      finalizeStream()
      setMessages(m => [...m, assistantTurn(`Error: ${e?.message ?? 'request failed'}`)])
    } finally {
      setSending(false)
    }
  }

  async function confirm(confirmed: boolean) {
    if (!businessId || activeId == null || !pending) return
    setPending(null)
    setSending(true)
    startStream()
    try {
      await chatApi.streamResume(businessId, activeId, confirmed, handleEvent)
    } catch (e: any) {
      finalizeStream()
      setMessages(m => [...m, assistantTurn(`Error: ${e?.message ?? 'request failed'}`)])
    } finally {
      setSending(false)
    }
  }

  function newChat() {
    setActiveId(null)
    setMessages([])
    setInput('')
    setPending(null)
    setStreaming(null)
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  if (!businessId) {
    return <div className="p-6 text-gray-500">Select a business first.</div>
  }

  const isWrite = pending?.type === 'write_confirm'

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
          {messages.length === 0 && !streaming && (
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
            {streaming && <StreamingBubble streaming={streaming} />}
            <div ref={bottomRef} />
          </div>
        </div>

        {pending && (
          <div className={`border-t px-6 py-3 ${isWrite ? 'border-orange-200 bg-orange-50' : 'border-amber-200 bg-amber-50'}`}>
            <div className="mx-auto flex max-w-2xl items-center gap-3">
              <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-lg ${isWrite ? 'bg-orange-100' : 'bg-amber-100'}`}>
                {isWrite ? '✍️' : '📊'}
              </div>
              <div className={`flex-1 text-sm ${isWrite ? 'text-orange-900' : 'text-amber-900'}`}>
                {isWrite ? (
                  <>
                    <span className="font-medium">Confirm this change:</span>{' '}
                    {pending.summary}
                    <span className="ml-1 text-xs opacity-70">(this updates your data)</span>
                  </>
                ) : (
                  <>Ready to generate: <strong>{pending.description}</strong></>
                )}
              </div>
              <button
                onClick={() => confirm(false)}
                disabled={sending}
                className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={() => confirm(true)}
                disabled={sending}
                className={`rounded-md px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 ${
                  isWrite ? 'bg-orange-600 hover:bg-orange-700' : 'bg-blue-600 hover:bg-blue-700'
                }`}
              >
                {isWrite ? 'Confirm' : 'Approve'}
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
              placeholder={pending ? 'Confirm or cancel the action above…' : 'Ask about your finances…'}
              disabled={!!pending}
              className="min-h-[24px] flex-1 resize-none border-0 bg-transparent px-1 py-1.5 text-sm text-gray-800 placeholder:text-gray-400 focus:outline-none focus:ring-0 disabled:opacity-50"
            />
            <button
              onClick={send}
              disabled={sending || !input.trim() || !!pending}
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

// Friendly label for the live trace; only tool calls are shown (steps are noise).
function traceLabel(ev: StreamEvent): string {
  if (ev.name === 'load_skill') return `Loaded skill: ${ev.args?.name ?? ''}`
  const map: Record<string, string> = {
    query_database: 'Querying the ledger',
    calculate_report: 'Computing report',
    transition_transaction: 'Preparing a transaction change',
    manage_configuration: 'Preparing a rule change',
    remember: 'Saving to memory',
    recall: 'Recalling saved notes',
    request_chart: 'Preparing a chart',
  }
  return ev.name ? map[ev.name] ?? `Using ${ev.name}` : ''
}

function StreamingBubble({ streaming }: { streaming: Streaming }) {
  return (
    <div className="flex items-start gap-3">
      <AssistantAvatar />
      <div className="min-w-0 flex-1 space-y-2">
        {streaming.trace.length > 0 && (
          <div className="space-y-1">
            {streaming.trace.map((t, i) => (
              <div key={i} className="flex items-center gap-1.5 text-xs text-gray-400">
                <Check /> {t}
              </div>
            ))}
          </div>
        )}
        {streaming.text ? (
          <div className="prose prose-sm max-w-none text-sm text-gray-800 prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-li:my-0 prose-table:text-xs">
            <ReactMarkdown>{streaming.text}</ReactMarkdown>
          </div>
        ) : (
          <ThinkingDots />
        )}
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
    <div className="flex w-fit items-center gap-1 rounded-2xl bg-gray-100 px-4 py-3">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400" />
    </div>
  )
}

function Check() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  )
}

function ArrowUp() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  )
}
