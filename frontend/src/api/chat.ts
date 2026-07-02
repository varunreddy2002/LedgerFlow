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

export interface ChatResponse {
  session_id: number
  answer: string
}

export const chatApi = {
  send: (businessId: number, message: string, sessionId: number | null) =>
    api.post<ChatResponse>(`/businesses/${businessId}/chat`, {
      message,
      session_id: sessionId,
    }),

  listSessions: (businessId: number) =>
    api.get<ChatSession[]>(`/businesses/${businessId}/chat/sessions`),

  getMessages: (sessionId: number) =>
    api.get<ChatTurn[]>(`/chat/sessions/${sessionId}/messages`),
}
