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

export async function runAgent<T = Record<string, unknown>>(payload: AgentRunRequest) {
  const { data } = await api.post<AgentRunResponse<T>>('/agent/run', payload)
  return data
}

export async function cancelAgentRun(runId: string) {
  const { data } = await api.post<{ run_id: string; cancelled: boolean; status: string }>(`/agent/runs/${runId}/cancel`)
  return data
}
