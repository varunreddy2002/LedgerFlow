import { api } from './client'

export interface ChatTurn {
  id: number
  role: 'user' | 'assistant'
  message: string
  agent_name?: string | null
  created_at: string
}

export interface ChatSession {
  id: number
  business_id: number
  title?: string | null
  created_at: string
}

// Chart pauses carry `description`; write pauses carry `summary` + `tool`.
export interface ChatInterrupt {
  type: 'chart_confirm' | 'write_confirm' | string
  description?: string
  summary?: string
  tool?: string
}

export interface ChatResponse {
  session_id: number
  status: 'done' | 'pending_chart'
  answer?: string | null
  chart_image?: string | null
  interrupt?: ChatInterrupt | null
}

// One frame of the agent's live reasoning trace (see backend streaming.py).
export interface StreamEvent {
  type: 'session' | 'step' | 'tool_call' | 'tool_result' | 'token' | 'interrupt' | 'done' | 'error'
  session_id?: number
  node?: string
  name?: string
  args?: Record<string, any>
  content?: string
  text?: string
  payload?: ChatInterrupt
  answer?: string
  chart_image?: string | null
  message?: string
}

// POST + read a text/event-stream, invoking onEvent per `data:` frame.
// (EventSource can't POST, so we stream the fetch body manually.)
async function streamPost(
  path: string,
  body: unknown,
  onEvent: (ev: StreamEvent) => void,
) {
  const res = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => res.statusText)
    throw new Error(detail || `HTTP ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const flush = (frame: string) => {
    const line = frame.split('\n').find(l => l.startsWith('data:'))
    if (!line) return
    const json = line.slice(5).trim()
    if (!json) return
    try {
      onEvent(JSON.parse(json) as StreamEvent)
    } catch {
      /* ignore malformed frame */
    }
  }

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) flush(frame)
  }
  if (buffer.trim()) flush(buffer)
}

export const chatApi = {
  streamSend: (
    businessId: number,
    message: string,
    sessionId: number | null,
    onEvent: (ev: StreamEvent) => void,
  ) =>
    streamPost(`/businesses/${businessId}/chat/stream`, { message, session_id: sessionId }, onEvent),

  streamResume: (
    businessId: number,
    sessionId: number,
    confirmed: boolean,
    onEvent: (ev: StreamEvent) => void,
  ) =>
    streamPost(
      `/businesses/${businessId}/chat/resume/stream`,
      { session_id: sessionId, confirmed },
      onEvent,
    ),

  listSessions: (businessId: number) =>
    api.get<ChatSession[]>(`/businesses/${businessId}/chat/sessions`),

  getMessages: (sessionId: number) =>
    api.get<ChatTurn[]>(`/chat/sessions/${sessionId}/messages`),
}
