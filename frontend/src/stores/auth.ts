import { defineStore } from 'pinia'
import { login as loginApi, me as meApi, register as registerApi, type UserResponse } from '../services/auth'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as UserResponse | null,
    token: localStorage.getItem('ef_token') || '',
  }),
  getters: {
    isLoggedIn: (state) => Boolean(state.token),
  },
  actions: {
    async login(payload: { username: string; password: string }) {
      const data = await loginApi(payload)
      this.token = data.access_token
      localStorage.setItem('ef_token', data.access_token)
      this.user = await meApi()
      return data
    },
    async register(payload: { username: string; password: string }) {
      return registerApi(payload)
    },
    async loadMe() {
      if (!this.token) return null
      this.user = await meApi()
      return this.user
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('ef_token')
    },
  },
})
