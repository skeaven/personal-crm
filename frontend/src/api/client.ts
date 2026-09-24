/**
 * API 客户端：统一携带令牌、统一错误消息、401 跳登录。
 * 后端契约见 backend/app/api；业务模块各自封装调用函数。
 */
import { useAuthStore } from '@/stores/auth'

const API_BASE = '/api/v1'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const auth = useAuthStore()
  const headers = new Headers(options.headers)
  headers.set('Content-Type', 'application/json')
  if (auth.token) {
    headers.set('Authorization', `Bearer ${auth.token}`)
  }

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })

  if (response.status === 401) {
    auth.logout()
    throw new ApiError('请先登录', 401)
  }
  if (response.status === 204) {
    return undefined as T
  }

  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError((body as { message?: string }).message ?? '请求失败', response.status)
  }
  return body as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: 'POST', body: data === undefined ? undefined : JSON.stringify(data) }),
  put: <T>(path: string, data: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(data) }),
  patch: <T>(path: string, data: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
