import { api } from './api'

export interface ModelRecord {
  id: string
  name: string
  model_id: string
  api_key_preview?: string
  base_url?: string | null
  enabled: boolean
  supports_vision: boolean
  kind: 'chat' | 'embedding' | 'rerank'
  dimensions?: number | null
  is_default: boolean
}

export interface PromptRecord {
  id: string
  step_code: string
  version: number
  title: string
  content: string
  is_active: boolean
}

export interface KbRecord {
  id: string
  step_code: string
  version: number
  name: string
  storage_ref: string
  is_active: boolean
}

export interface AdminStepRecord {
  code: string
  order: number
  name: string
  admin_focus: string
  supports_sub_prompts: boolean
  module_order_editable: boolean
  prompt_count: number
  kb_count: number
  active_prompt_id?: string | null
  active_kb_id?: string | null
  module_order: string[]
}

export interface ActiveStepConfig {
  step_code: string
  active_prompt: PromptRecord | null
  active_kb: KbRecord | null
  prompt_text: string
  knowledge_text: string
  prompt_title: string
  kb_name: string
}

export interface ChangeLogRecord {
  id: string
  actor_user_id: string
  actor_username?: string
  action: string
  target_type: string
  target_id: string
  before_data?: Record<string, unknown> | null
  after_data?: Record<string, unknown> | null
  created_at?: string | null
  summary?: string
}

export interface StepConfigSavePayload {
  prompt_title: string
  prompt_content: string
  kb_name: string
  kb_content: string
  action?: 'save' | 'preview'
}

export async function listAdminSteps() {
  const { data } = await api.get<{ items: AdminStepRecord[] }>('/admin/steps')
  return data.items
}

export async function getAdminStep(stepCode: string) {
  const { data } = await api.get<AdminStepRecord & { prompts: PromptRecord[]; kbs: KbRecord[] }>(`/admin/steps/${stepCode}`)
  return data
}

export async function getActiveStepConfig(stepCode: string) {
  const { data } = await api.get<ActiveStepConfig>(`/admin/steps/${stepCode}/active-config`)
  return data
}

export async function saveStepConfig(stepCode: string, payload: StepConfigSavePayload) {
  const { data } = await api.post<{
    step: AdminStepRecord & { prompts: PromptRecord[]; kbs: KbRecord[] }
    graph_result: Record<string, unknown>
    change_entries: Array<Record<string, unknown>>
  }>(`/admin/steps/${stepCode}/config`, payload)
  return data
}

export async function listChangeLogs(params?: { step_code?: string; target_type?: string; limit?: number }) {
  const { data } = await api.get<{ items: ChangeLogRecord[] }>('/admin/change-logs', { params })
  return data.items
}

export async function updateModuleOrder(stepCode: string, moduleOrder: string[]) {
  const { data } = await api.put<AdminStepRecord & { prompts: PromptRecord[]; kbs: KbRecord[] }>(`/admin/steps/${stepCode}/module-order`, { module_order: moduleOrder })
  return data
}

export async function listModels() {
  const { data } = await api.get<{ items: ModelRecord[] }>('/admin/models')
  return data.items
}

export async function createModel(payload: Record<string, unknown>) {
  const { data } = await api.post('/admin/models', payload)
  return data
}

export async function updateModel(modelId: string, payload: Record<string, unknown>) {
  const { data } = await api.patch(`/admin/models/${modelId}`, payload)
  return data
}

export async function toggleModel(modelId: string, enabled: boolean) {
  const { data } = await api.patch(`/admin/models/${modelId}`, { enabled })
  return data
}

export async function deleteModel(modelId: string) {
  const { data } = await api.delete(`/admin/models/${modelId}`)
  return data
}

export async function setDefaultModel(modelId: string) {
  const { data } = await api.post(`/admin/models/${modelId}/set-default`)
  return data
}

export async function listPrompts(stepCode?: string) {
  const { data } = await api.get<{ items: PromptRecord[] }>('/admin/prompts', { params: stepCode ? { step_code: stepCode } : undefined })
  return data.items
}

export async function createPrompt(payload: Record<string, unknown>) {
  const { data } = await api.post('/admin/prompts', payload)
  return data
}

export async function updatePrompt(promptId: string, payload: { title?: string; content?: string }) {
  const { data } = await api.patch(`/admin/prompts/${promptId}`, payload)
  return data
}

export async function activatePrompt(promptId: string) {
  const { data } = await api.patch(`/admin/prompts/${promptId}/activate`)
  return data
}

export async function deletePrompt(promptId: string) {
  const { data } = await api.delete(`/admin/prompts/${promptId}`)
  return data
}

export async function listKbs(stepCode?: string) {
  const { data } = await api.get<{ items: KbRecord[] }>('/admin/kbs', { params: stepCode ? { step_code: stepCode } : undefined })
  return data.items
}

export async function createKb(payload: Record<string, unknown>) {
  const { data } = await api.post('/admin/kbs', payload)
  return data
}

export async function updateKb(kbId: string, payload: { name?: string; storage_ref?: string }) {
  const { data } = await api.patch(`/admin/kbs/${kbId}`, payload)
  return data
}

export async function activateKb(kbId: string) {
  const { data } = await api.patch(`/admin/kbs/${kbId}/activate`)
  return data
}

export async function deleteKb(kbId: string) {
  const { data } = await api.delete(`/admin/kbs/${kbId}`)
  return data
}

export interface DashboardStats {
  users: { total: number; active: number }
  projects: number
  llm_calls: number
  total_tokens: number
  tasks: { total: number; failed: number; failure_rate: number }
  recent_events: ChangeLogRecord[]
}

export async function getDashboardStats() {
  const { data } = await api.get<DashboardStats>('/admin/dashboard/stats')
  return data
}
