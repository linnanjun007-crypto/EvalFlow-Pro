import { api } from './api'

export interface UsageSummary {
  user_id: string
  projects: { total: number; active: number }
  files: number
  steps_generated: number
  tasks: { total: number; succeeded: number; failed: number; failure_rate: number }
  llm: {
    calls: number
    total_tokens: number
    prompt_tokens: number
    completion_tokens: number
    avg_latency_ms: number
  }
  by_step: Array<{ step_code: string; calls: number; total_tokens: number }>
  by_model: Array<{ model_name: string; calls: number; total_tokens: number }>
}

export async function getUsageSummary() {
  const { data } = await api.get<UsageSummary>('/usage')
  return data
}
