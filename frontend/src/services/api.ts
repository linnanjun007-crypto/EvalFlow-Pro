import axios from 'axios'

const baseURL =
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? '/api/v1' : 'http://localhost:8000/api/v1')

export const api = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('ef_token')
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const data = error?.response?.data
    if (data instanceof Blob) {
      try {
        const text = await data.text()
        const parsed = JSON.parse(text) as { detail?: string; message?: string }
        return Promise.reject(new Error(parsed.detail || parsed.message || '请求失败'))
      } catch {
        return Promise.reject(new Error(error.message || '请求失败'))
      }
    }
    const message = data?.detail || data?.message || error.message || '请求失败'
    return Promise.reject(new Error(message))
  },
)
