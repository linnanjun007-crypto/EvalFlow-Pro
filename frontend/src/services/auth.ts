import { api } from './api'

export interface LoginRequest {
  username: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface UserResponse {
  id: string
  username: string
  role: string
  status?: string
}

export interface UserStatusUpdateRequest {
  status: 'active' | 'disabled'
}

export async function register(payload: LoginRequest) {
  const { data } = await api.post<UserResponse>('/auth/register', payload)
  return data
}

export async function login(payload: LoginRequest) {
  const { data } = await api.post<TokenResponse>('/auth/login', payload)
  return data
}

export async function me() {
  const { data } = await api.get<UserResponse>('/auth/me')
  return data
}

export async function listUsers() {
  const { data } = await api.get<{ items: UserResponse[] }>('/auth/users')
  return data.items
}

export async function setUserStatus(userId: string, status: UserStatusUpdateRequest['status']) {
  const { data } = await api.patch(`/auth/users/${userId}/status`, { status })
  return data
}
