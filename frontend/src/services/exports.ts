import { api } from './api'
import type { FileRecord } from './files'

export type ExportFormat = 'markdown' | 'docx'

export interface Step1ExportRequest {
  user_id?: string
  project_name: string
  thread_id: string
  content_text: string
  content_json?: string | null
  export_style: 'classic' | 'custom'
  export_format?: ExportFormat
  custom_title?: string | null
  save_to_database?: boolean
  draft_payload?: Record<string, unknown> | null
}

export interface Step1ExportResponse {
  project_id: string
  file_name: string
  storage_key: string
  download_url: string
  file_record?: FileRecord | null
  metadata: Record<string, unknown>
}

export async function exportStep1(projectId: string, payload: Step1ExportRequest) {
  const { data } = await api.post<Step1ExportResponse>(`/exports/step1/${projectId}`, payload)
  return data
}

export interface Step2FormatOptions {
  font_family?: string
  font_size_pt?: number
  heading_font_size_pt?: number
  line_spacing?: number
  paragraph_spacing_pt?: number
  first_line_indent_chars?: number
}

export interface Step2ExportRequest {
  user_id?: string
  project_name: string
  thread_id: string
  content_text: string
  content_json?: string | null
  export_style: 'classic' | 'custom'
  export_format?: ExportFormat
  custom_title?: string | null
  save_to_database?: boolean
  draft_payload?: Record<string, unknown> | null
  categories?: string[] | null
  format_options?: Step2FormatOptions | null
}

export type Step2ExportResponse = Step1ExportResponse

export async function exportStep2(projectId: string, payload: Step2ExportRequest) {
  const { data } = await api.post<Step2ExportResponse>(`/exports/step2/${projectId}`, payload)
  return data
}

function encodeExportFilenameInPath(path: string) {
  const match = path.match(/^(\/exports\/download\/[^/]+)\/(.+)$/)
  if (!match) return path
  const prefix = match[1]
  const rawFilename = decodeURIComponent(match[2])
  return `${prefix}/${encodeURIComponent(rawFilename)}`
}

function toExportDownloadPath(downloadUrl: string) {
  const trimmed = downloadUrl.trim()
  let path = trimmed
  if (/^https?:\/\//i.test(trimmed)) {
    try {
      path = new URL(trimmed).pathname
    } catch {
      path = trimmed
    }
  }
  if (path.startsWith('/api/v1/')) path = path.slice('/api/v1'.length)
  if (!path.startsWith('/')) path = `/${path}`
  return encodeExportFilenameInPath(path)
}

async function readBlobErrorMessage(blob: Blob) {
  try {
    const text = await blob.text()
    const parsed = JSON.parse(text) as { detail?: string; message?: string }
    return parsed.detail || parsed.message || text
  } catch {
    return '下载失败，服务器返回了无效文件'
  }
}

function fileExtension(name: string): string {
  const idx = name.lastIndexOf('.')
  return idx >= 0 ? name.slice(idx + 1).toLowerCase() : ''
}

async function assertExportBlob(blob: Blob, fileName: string) {
  if (!(blob instanceof Blob) || blob.size === 0) {
    throw new Error('下载失败，文件为空')
  }
  const ext = fileExtension(fileName)
  if (ext === 'md' || ext === 'markdown' || ext === 'txt') {
    if (blob.type.includes('json')) {
      throw new Error(await readBlobErrorMessage(blob))
    }
    return
  }
  if (blob.size < 4) throw new Error('下载失败，文件为空')
  const header = new Uint8Array(await blob.slice(0, 4).arrayBuffer())
  const isZipDocx = header[0] === 0x50 && header[1] === 0x4b
  if (isZipDocx) return
  if (blob.type.includes('json')) {
    throw new Error(await readBlobErrorMessage(blob))
  }
  const looksDocx =
    blob.type.includes('wordprocessingml') ||
    blob.type.includes('officedocument') ||
    blob.type === 'application/octet-stream' ||
    blob.type === ''
  if (!looksDocx) {
    throw new Error('下载失败，返回内容不是有效的导出文件')
  }
}

function triggerBrowserDownload(blob: Blob, fileName: string) {
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = fileName
  anchor.style.display = 'none'
  document.body.appendChild(anchor)
  anchor.click()
  window.setTimeout(() => {
    anchor.remove()
    URL.revokeObjectURL(objectUrl)
  }, 2000)
}

export interface Step14ExportRequest {
  project_name: string
  content_text: string
  custom_title?: string | null
  export_format?: ExportFormat
  save_to_database?: boolean
}

export type Step14ExportResponse = Step1ExportResponse

export async function exportStep14Word(projectId: string, payload: Step14ExportRequest) {
  const { data } = await api.post<Step14ExportResponse>(`/exports/step14/${projectId}`, payload)
  return data
}

export async function downloadExportFile(downloadUrl: string, fileName: string) {
  const path = toExportDownloadPath(downloadUrl)
  const ext = fileExtension(fileName)
  const accept = ext === 'md' || ext === 'markdown' || ext === 'txt'
    ? 'text/markdown, text/plain;q=0.9, */*;q=0.8'
    : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document, */*;q=0.8'
  const response = await api.get(path, {
    responseType: 'blob',
    headers: { Accept: accept },
  })
  const blob = response.data as Blob
  await assertExportBlob(blob, fileName)
  triggerBrowserDownload(blob, fileName)
}

export interface GenericStepPdfRequest {
  project_name: string
  content_text: string
  custom_title?: string | null
  project_id?: string | null
  save_to_database?: boolean
}

export async function exportStepPdf(stepCode: string, payload: GenericStepPdfRequest) {
  const response = await api.post(`/exports/${stepCode}/pdf`, payload, { responseType: 'blob' })
  const blob = response.data as Blob
  const fileName = `${payload.project_name || stepCode}_${stepCode}.pdf`
  triggerBrowserDownload(blob, fileName)
}
