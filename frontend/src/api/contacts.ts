/** 联系人模块 API 封装：对应 backend contacts/api.py */
import { api } from './client'
import type {
  ContactCreate,
  ContactCreateResponse,
  ContactDetailOut,
  ContactOut,
  ContactUpdate,
  DuplicateWarning,
  ImportantDateCreate,
  ImportantDateUpdate,
  MapPointsOut,
} from './types'

export const contactsApi = {
  /** 毕业院校去重列表（校友查找/表单选择数据源）。 */
  schools: () => api.get<string[]>('/contacts/schools'),
  /** 地图页数据：坐标撒点 + 省份计数聚合（choropleth）。 */
  mapPoints: () => api.get<MapPointsOut>('/contacts/map-points'),
  list: (params?: { tier?: string; search?: string; activity?: string }) => {
    const query = new URLSearchParams()
    if (params?.tier) query.set('tier', params.tier)
    if (params?.search) query.set('search', params.search)
    if (params?.activity) query.set('activity', params.activity)
    const qs = query.toString()
    return api.get<ContactOut[]>(`/contacts${qs ? `?${qs}` : ''}`)
  },
  get: (id: number) => api.get<ContactDetailOut>(`/contacts/${id}`),
  create: (data: ContactCreate) => api.post<ContactCreateResponse>('/contacts', data),
  update: (id: number, data: ContactUpdate) => api.patch<ContactDetailOut>(`/contacts/${id}`, data),
  promote: (id: number) => api.post<ContactDetailOut>(`/contacts/${id}/promote`),
  archive: (id: number) => api.delete<void>(`/contacts/${id}`),
  duplicateCheck: (params: { name?: string; nickname?: string | null }) => {
    const query = new URLSearchParams()
    if (params.name) query.set('name', params.name)
    if (params.nickname) query.set('nickname', params.nickname)
    const qs = query.toString()
    return api.get<DuplicateWarning[]>(`/contacts/duplicate-check${qs ? `?${qs}` : ''}`)
  },
  createDate: (contactId: number, data: ImportantDateCreate) =>
    api.post<ContactDetailOut>(`/contacts/${contactId}/dates`, data),
  updateDate: (contactId: number, dateId: number, data: ImportantDateUpdate) =>
    api.patch<ContactDetailOut>(`/contacts/${contactId}/dates/${dateId}`, data),
  removeDate: (contactId: number, dateId: number) =>
    api.delete<void>(`/contacts/${contactId}/dates/${dateId}`),
}
