import { api } from './api'

export interface DownloadRecord {
  id: string
  file_id: string
  file_name: string
  status: string
  created_at?: string | null
}

export async function listDownloads() {
  const { data } = await api.get<{ items: DownloadRecord[] }>('/downloads')
  return data.items
}

export async function getDownload(downloadId: string) {
  const { data } = await api.get<DownloadRecord>(`/downloads/${downloadId}`)
  return data
}
