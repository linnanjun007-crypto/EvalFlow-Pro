import { api } from './api'

export interface UserKb {
  id: string
  user_id: string
  name: string
  description: string | null
  embedding_model_id: string
  embedding_dim: number
  chunk_size: number
  chunk_overlap: number
  status: string
  created_at: string | null
  updated_at: string | null
  doc_count?: number
  chunk_count?: number
}

export interface KbDocument {
  id: string
  kb_id: string
  source_file_id: string | null
  source_type: string
  file_name: string
  file_type: string
  file_size: number | null
  chunk_count: number
  status: string
  error_message: string | null
  created_at: string | null
  indexed_at: string | null
}

export interface KbSearchResult {
  id: number
  document_id: string
  chunk_index: number
  content: string
  file_name: string
  score: number
}

export interface KbChunk {
  id: number
  chunk_index: number
  content: string
  char_count: number
  metadata: Record<string, unknown> | null
}

export interface KbChunksResponse {
  items: KbChunk[]
  total: number
  offset: number
  limit: number
}

export function listKbs() {
  return api.get<{ items: UserKb[] }>('/kbs').then((r) => r.data.items)
}

export function createKb(name: string, description = '') {
  return api.post<UserKb>('/kbs', { name, description }).then((r) => r.data)
}

export function getKb(kbId: string) {
  return api.get<UserKb>(`/kbs/${kbId}`).then((r) => r.data)
}

export function updateKb(kbId: string, data: { name?: string; description?: string }) {
  return api.patch<UserKb>(`/kbs/${kbId}`, data).then((r) => r.data)
}

export function deleteKb(kbId: string) {
  return api.delete(`/kbs/${kbId}`)
}

export function listKbDocuments(kbId: string) {
  return api.get<{ items: KbDocument[] }>(`/kbs/${kbId}/documents`).then((r) => r.data.items)
}

export function uploadKbDocument(kbId: string, file: File) {
  const form = new FormData()
  form.append('upload', file)
  return api
    .post(`/kbs/${kbId}/documents/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    .then((r) => r.data)
}

export function promoteProjectFileToKb(kbId: string, fileId: string) {
  return api.post(`/kbs/${kbId}/documents/promote`, { file_id: fileId }).then((r) => r.data)
}

export function reindexKbDocument(kbId: string, docId: string) {
  return api.post(`/kbs/${kbId}/documents/${docId}/reindex`).then((r) => r.data)
}

export function deleteKbDocument(kbId: string, docId: string) {
  return api.delete(`/kbs/${kbId}/documents/${docId}`)
}

export function getKbDocumentDetail(kbId: string, docId: string) {
  return api.get<KbDocument>(`/kbs/${kbId}/documents/${docId}`).then((r) => r.data)
}

export function listKbDocumentChunks(
  kbId: string,
  docId: string,
  offset = 0,
  limit = 50,
) {
  return api
    .get<KbChunksResponse>(`/kbs/${kbId}/documents/${docId}/chunks`, {
      params: { offset, limit },
    })
    .then((r) => r.data)
}

export function searchKb(kbId: string, query: string, topK = 5) {
  return api
    .post<{ items: KbSearchResult[]; query: string; top_k: number }>(`/kbs/${kbId}/search`, {
      query,
      top_k: topK,
    })
    .then((r) => r.data)
}

export function getProjectKbs(projectId: string) {
  return api.get<{ items: UserKb[] }>(`/projects/${projectId}/kbs`).then((r) => r.data.items)
}

export function setProjectKbs(projectId: string, kbIds: string[]) {
  return api
    .put<{ items: UserKb[] }>(`/projects/${projectId}/kbs`, { kb_ids: kbIds })
    .then((r) => r.data.items)
}
