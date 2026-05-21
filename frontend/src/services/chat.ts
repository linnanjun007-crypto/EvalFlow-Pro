import { api } from './api'

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface ChatRequest {
  project_id: string
  step_code: string
  messages: ChatMessage[]
  user_message: string
  workflow_role?: string
  workflow_state?: Record<string, unknown>
}

export interface ChatResponse {
  project_id: string
  step_code: string
  answer: string
  status: string
  title?: string | null
  fallback_step_code?: string | null
}

export async function sendChat(payload: ChatRequest) {
  const { data } = await api.post<ChatResponse>('/chat/send', payload)
  return data
}
