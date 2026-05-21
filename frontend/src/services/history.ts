import { api } from './api'

export interface HistoryRecord {
  id?: string
  time: string | null
  project_id: string
  project: string
  step: string
  summary: string
  title: string
  content_text?: string
}

export interface HistoryDetail extends HistoryRecord {
  content_text: string
}

export async function listHistory(params: { keyword?: string } = {}) {
  const { data } = await api.get<{ items: HistoryRecord[] }>('/history', { params })
  return data.items
}

export async function getHistory(historyId: string) {
  const { data } = await api.get<HistoryDetail | { id: string; status: string }>(`/history/${historyId}`)
  return data
}
