/** gifts 模块 API 封装：礼物往来与愿望清单，对应 backend gifts/api.py */
import { api } from './client'
import type {
  GiftCreate,
  GiftDirection,
  GiftOut,
  GiftUpdate,
  WishlistConvertOut,
  WishlistCreate,
  WishlistOut,
  WishlistStatus,
  WishlistUpdate,
} from './types'

function withQuery(path: string, params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  const qs = query.toString()
  return qs ? `${path}?${qs}` : path
}

export const giftsApi = {
  list: (params?: {
    search?: string
    direction?: GiftDirection
    contactId?: number
    limit?: number
    offset?: number
  }) =>
    api.listPaged<GiftOut>(
      withQuery('/gifts', {
        search: params?.search,
        direction: params?.direction,
        contact_id: params?.contactId,
        limit: params?.limit,
        offset: params?.offset,
      }),
    ),
  get: (id: number) => api.get<GiftOut>(`/gifts/${id}`),
  create: (data: GiftCreate) => api.post<GiftOut>('/gifts', data),
  update: (id: number, data: GiftUpdate) => api.patch<GiftOut>(`/gifts/${id}`, data),
  remove: (id: number) => api.delete<void>(`/gifts/${id}`),
}

export const wishlistApi = {
  list: (params?: { search?: string; status?: WishlistStatus; contact_id?: number }) =>
    api.get<WishlistOut[]>(
      withQuery('/gifts/wishlist', {
        search: params?.search,
        status: params?.status,
        contact_id: params?.contact_id,
      }),
    ),
  create: (data: WishlistCreate) => api.post<WishlistOut>('/gifts/wishlist', data),
  update: (id: number, data: WishlistUpdate) =>
    api.patch<WishlistOut>(`/gifts/wishlist/${id}`, data),
  remove: (id: number) => api.delete<void>(`/gifts/wishlist/${id}`),
  convert: (id: number) => api.post<WishlistConvertOut>(`/gifts/wishlist/${id}/convert`),
}
