import { api } from './api'

export interface StepGeneratePayload {
  project_id: string
  workflow_role?: string
  review_mode?: string | null
  review_feedback?: string | null
  payload?: Record<string, unknown>
}

export interface StepGenerateResponse {
  task_id?: string | null
  step_code: string
  message: string
  status: string
}

export interface StepResultPayload {
  id: string
  title: string
  content_json: string
  content_text: string
  version: number
  is_final: boolean
}

export interface StepResultResponse {
  project_id: string
  step_code: string
  status: string
  result: StepResultPayload | Record<string, never>
}

export interface StepStatusItem {
  step_code: string
  status: 'not_found' | 'draft' | 'succeeded'
  done: boolean
  version?: number | null
  title?: string | null
}

export interface WorkflowStatusResponse {
  project_id: string
  total_steps: number
  done_steps: number
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled'
  progress: number
  steps: StepStatusItem[]
}

export async function generateStep(stepCode: string, payload: StepGeneratePayload) {
  const { data } = await api.post<StepGenerateResponse>(`/steps/${stepCode}/generate`, payload)
  return data
}

export async function getWorkflowStatus(projectId: string) {
  const { data } = await api.get<WorkflowStatusResponse>('/steps/status', {
    params: { project_id: projectId },
  })
  return data
}

export async function getStepResult(stepCode: string, projectId: string) {
  const { data } = await api.get<StepResultResponse>(`/steps/${stepCode}/result`, {
    params: { project_id: projectId },
  })
  return data
}

export interface StepSavePayload {
  project_id: string
  title: string
  content_text: string
  content_json?: string
  model_name?: string
}

export async function saveStepResult(stepCode: string, payload: StepSavePayload) {
  const { data } = await api.post<StepResultPayload>(`/steps/${stepCode}/save`, payload)
  return data
}

export async function listStepHistories(stepCode: string, projectId: string) {
  const { data } = await api.get<{ items: StepResultPayload[] }>(`/steps/${stepCode}/histories`, {
    params: { project_id: projectId },
  })
  return data.items
}

export async function deleteStepHistory(stepCode: string, projectId: string, outputId: string) {
  const { data } = await api.delete(`/steps/${stepCode}/histories/${outputId}`, {
    params: { project_id: projectId },
  })
  return data
}
