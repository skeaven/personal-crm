/** funds 模块 API 封装：资金往来，对应 backend funds/api.py */
import { api } from './client'
import type {
  FundCategory,
  FundDirection,
  FundFlowCreate,
  FundFlowOut,
  FundFlowUpdate,
  FundStatus,
} from './types'

function withQuery(path: string, params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  const qs = query.toString()
  return qs ? `${path}?${qs}` : path
}

export const fundsApi = {
  list: (params?: {
    search?: string
    direction?: FundDirection
    category?: FundCategory
    status?: FundStatus
    contactId?: number
    limit?: number
    offset?: number
  }) =>
    api.listPaged<FundFlowOut>(
      withQuery('/funds', {
        search: params?.search,
        direction: params?.direction,
        category: params?.category,
        status: params?.status,
        contact_id: params?.contactId,
        limit: params?.limit,
        offset: params?.offset,
      }),
    ),
  get: (id: number) => api.get<FundFlowOut>(`/funds/${id}`),
  create: (data: FundFlowCreate) => api.post<FundFlowOut>('/funds', data),
  update: (id: number, data: FundFlowUpdate) => api.patch<FundFlowOut>(`/funds/${id}`, data),
  remove: (id: number) => api.delete<void>(`/funds/${id}`),
}
