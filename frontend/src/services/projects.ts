import { api } from './api'

export interface ProjectCreateRequest {
  name: string
  description?: string | null
}

export interface ProjectResponse {
  id: string
  name: string
  description?: string | null
  status?: string | null
}

export interface ProjectUpdateRequest {
  name?: string | null
  description?: string | null
  status?: string | null
}

export interface ProjectCreateResponse extends ProjectResponse {}

export async function listProjects() {
  const { data } = await api.get<{ items: ProjectResponse[] }>('/projects')
  return data.items
}

export async function createProject(payload: ProjectCreateRequest) {
  const { data } = await api.post<ProjectResponse>('/projects', payload)
  return data
}

export async function getProject(projectId: string) {
  const { data } = await api.get<ProjectResponse>(`/projects/${projectId}`)
  return data
}

export async function updateProject(projectId: string, payload: ProjectUpdateRequest) {
  const { data } = await api.patch<ProjectResponse>(`/projects/${projectId}`, payload)
  return data
}

export async function deleteProject(projectId: string) {
  const { data } = await api.delete<{ message: string }>(`/projects/${projectId}`)
  return data
}
