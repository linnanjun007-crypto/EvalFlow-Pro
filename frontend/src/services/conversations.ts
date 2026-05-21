import { api } from './api'

export interface ConversationRecord {
  id: string
  project_id: string
  step_code: string
  title: string
  status: string
}

export interface ConversationMessageRecord {
  id: string
  conversation_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  model_name?: string | null
}

export async function createConversation(payload: { project_id: string; step_code: string; title?: string | null; user_id?: string | null }) {
  const { data } = await api.post<ConversationRecord>('/conversations', payload)
  return data
}

export async function getConversation(conversationId: string) {
  const { data } = await api.get<{ conversation: ConversationRecord; messages: ConversationMessageRecord[] }>(`/conversations/${conversationId}`)
  return data
}

export async function sendConversationMessage(conversationId: string, content: string) {
  const { data } = await api.post<{ conversation_id: string; project_id: string; step_code: string; answer: string; status: string }>(`/conversations/${conversationId}/messages`, { role: 'user', content })
  return data
}
