/** 登录态 store：令牌与当前用户的持久化。 */
import { defineStore } from 'pinia'
import { api } from '@/api/client'
import type { LoginResponse, UserOut } from '@/api/types'

const TOKEN_KEY = 'crm_token'
const USER_KEY = 'crm_user'

function readStoredUser(): UserOut | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as UserOut
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) ?? '',
    user: readStoredUser(),
  }),
  getters: {
    isLoggedIn: (state) => Boolean(state.token),
  },
  actions: {
    /** 调登录接口并持久化令牌与用户信息。 */
    async login(username: string, password: string): Promise<void> {
      const data = await api.post<LoginResponse>('/auth/login', { username, password })
      this.token = data.access_token
      this.user = data.user
      localStorage.setItem(TOKEN_KEY, data.access_token)
      localStorage.setItem(USER_KEY, JSON.stringify(data.user))
    },
    /** 绑定/解绑"我是谁"（D15）：更新后端并同步本地持久化的用户信息。 */
    async bindContact(contactId: number | null): Promise<void> {
      const user = await api.put<UserOut>('/auth/me', { contact_id: contactId })
      this.user = user
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    },
    /** 清除登录态（登出或令牌失效）。 */
    logout(): void {
      this.token = ''
      this.user = null
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    },
  },
})
