import { defineStore } from 'pinia'
import { authApi } from '../api'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    user: null,
    assistantGreetingPending: false,
  }),
  getters: {
    isLoggedIn: (state) => !!state.token,
    hasCouple: (state) => !!state.user?.couple_id,
    isAdmin: (state) => !!state.user?.is_admin,
  },
  actions: {
    setToken(token) {
      this.token = token
      this.assistantGreetingPending = true
      localStorage.setItem('token', token)
    },
    async fetchUser() {
      if (!this.token) return null
      try {
        this.user = await authApi.me()
        return this.user
      } catch {
        this.logout()
        return null
      }
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('token')
    },
  },
})
