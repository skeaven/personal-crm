/**
 * API 客户端：统一携带令牌、统一错误消息、401 跳登录。
 * 后端契约见 backend/app/api；业务模块各自封装调用函数。
 */
import { useAuthStore } from '@/stores/auth'
import type { Paged } from './types'

const API_BASE = '/api/v1'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  onResponse?: (response: Response) => void,
): Promise<T> {
  const auth = useAuthStore()
  const headers = new Headers(options.headers)
  // FormData 必须由浏览器自己带 boundary；手动设 application/json 会让后端解析失败
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  if (auth.token) {
    headers.set('Authorization', `Bearer ${auth.token}`)
  }

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  onResponse?.(response)

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
  postForm: <T>(path: string, form: FormData) =>
    request<T>(path, { method: 'POST', body: form }),

  /** 分页列表：body 是数组，总数在 X-Total-Count 头里。 */
  listPaged: async <T>(path: string): Promise<Paged<T>> => {
    let total = 0
    const items = await request<T[]>(path, {}, (response) => {
      total = Number(response.headers.get('X-Total-Count') ?? 0)
    })
    return { items, total }
  },

  /** 上传单张图片到临时区，返回供表单引用的临时路径。 */
  uploadTemp: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ temp_path: string }>('/uploads/temp', { method: 'POST', body: form })
  },
}
