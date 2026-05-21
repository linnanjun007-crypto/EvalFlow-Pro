import { api } from './api'

export interface FileRecord {
  id: string
  project_id: string
  user_id: string
  project_name?: string | null
  file_name: string
  file_type: string
  storage_key: string
  parse_status: string
  source_type?: string | null
  file_size?: number | null
  metadata_json?: string | null
}

const NON_INPUT_SOURCE_TYPES = new Set(['step1_export_final', 'step1_draft_commit'])

export function isInputProjectFile(file: FileRecord) {
  const sourceType = (file.source_type || '').trim()
  if (sourceType && NON_INPUT_SOURCE_TYPES.has(sourceType)) return false
  if (file.file_type === 'draft-json') return false
  return true
}

export interface FileCreateRequest {
  user_id?: string
  project_name?: string | null
  file_name: string
  file_type: string
  storage_key?: string
  source_type?: string | null
  file_size?: number | null
  metadata_json?: string | null
  draft_thread_id?: string | null
  draft_payload?: Record<string, unknown> | null
}

export async function listFiles(projectId: string) {
  const { data } = await api.get<{ items: FileRecord[] }>(`/files/${projectId}`)
  return data.items
}

export async function createFileRecord(projectId: string, payload: FileCreateRequest) {
  const { data } = await api.post<FileRecord>(`/files/${projectId}`, payload)
  return data
}

export async function uploadProjectFile(projectId: string, file: File, userId = 'demo-user-id') {
  const form = new FormData()
  form.append('upload', file)
  const { data } = await api.post<FileRecord>(`/files/${projectId}/upload`, form, {
    params: { user_id: userId },
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function deleteFile(projectId: string, fileId: string) {
  const { data } = await api.delete(`/files/${projectId}/${fileId}`)
  return data
}
