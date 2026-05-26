import { api } from './api'

export interface AgentCapability {
  role: string
  step_code: string
  module: string
}

export interface AgentCapabilitiesResponse {
  graphs: AgentCapability[]
  roles: string[]
}

export interface AgentRunRequest {
  workflow_role?: string
  step_code: string
  payload?: Record<string, unknown>
  context?: Record<string, unknown>
}

export interface AgentRunResponse<T = Record<string, unknown>> {
  role: string
  step_code: string
  result: T
}

export async function getAgentCapabilities() {
  const { data } = await api.get<AgentCapabilitiesResponse>('/agent/capabilities')
  return data
}

export async function runAgent<T = Record<string, unknown>>(payload: AgentRunRequest, options?: { signal?: AbortSignal }) {
  const { data } = await api.post<AgentRunResponse<T>>('/agent/run', payload, { signal: options?.signal })
  return data
}

export async function cancelAgentRun(runId: string) {
  const { data } = await api.post<{ run_id: string; cancelled: boolean; status: string }>(`/agent/runs/${runId}/cancel`)
  return data
}

export async function getThreadState(params: { step_code: string; thread_id: string; role?: string }) {
  const { data } = await api.post<{ thread_id: string; state: Record<string, unknown> | null; found: boolean }>('/agent/state/get', params)
  return data
}

export async function updateThreadState(params: { step_code: string; thread_id: string; values: Record<string, unknown>; role?: string }) {
  const { data } = await api.post<{ thread_id: string; updated: boolean; keys: string[] }>('/agent/state/update', params)
  return data
}

export async function clearThreadState(params: { step_code: string; thread_id: string; project_id?: string; role?: string }) {
  const { data } = await api.post<{ thread_id: string; cleared: boolean; step_code: string }>('/agent/state/clear', params)
  return data
}
