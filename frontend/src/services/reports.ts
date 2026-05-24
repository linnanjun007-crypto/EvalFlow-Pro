import { api } from './api'

export interface ProjectReport {
  id: string
  user_id: string
  project_id: string
  project_name: string
  title: string
  retention_days: number
  expires_at: string | null
  generated_at: string | null
  created_at: string | null
  char_count: number
  content_md?: string
}

export function listReports() {
  return api.get<{ items: ProjectReport[] }>('/reports').then((r) => r.data.items)
}

export function getReport(reportId: string) {
  return api.get<ProjectReport>(`/reports/${reportId}`).then((r) => r.data)
}

export function updateReportRetention(reportId: string, retentionDays: number) {
  return api.patch<ProjectReport>(`/reports/${reportId}`, { retention_days: retentionDays }).then((r) => r.data)
}

export function deleteReport(reportId: string) {
  return api.delete(`/reports/${reportId}`)
}

export function exportReport(reportId: string, format: 'md' | 'txt' = 'md') {
  return api
    .get(`/reports/${reportId}/export`, {
      params: { format },
      responseType: 'blob',
    })
    .then((r) => r.data as Blob)
}

export function regenerateReport(projectId: string) {
  return api.post<ProjectReport>(`/reports/regenerate/${projectId}`).then((r) => r.data)
}
