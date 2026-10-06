/** records 模块 API 封装：活动（含参与者）、任务与备注，对应 backend records/api.py */
import { api } from './client'
import type {
  ActivityCreate,
  ActivityOut,
  ActivityUpdate,
  NoteCreate,
  NoteOut,
  NoteUpdate,
  TaskCreate,
  TaskOut,
  TaskStatus,
  TaskUpdate,
} from './types'

function withQuery(path: string, params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  const qs = query.toString()
  return qs ? `${path}?${qs}` : path
}

export const activitiesApi = {
  list: (params?: { search?: string; contactId?: number; limit?: number; offset?: number }) =>
    api.listPaged<ActivityOut>(
      withQuery('/records/activities', {
        search: params?.search,
        contact_id: params?.contactId,
        limit: params?.limit,
        offset: params?.offset,
      }),
    ),
  get: (id: number) => api.get<ActivityOut>(`/records/activities/${id}`),
  create: (data: ActivityCreate) => api.post<ActivityOut>('/records/activities', data),
  update: (id: number, data: ActivityUpdate) =>
    api.patch<ActivityOut>(`/records/activities/${id}`, data),
  remove: (id: number) => api.delete<void>(`/records/activities/${id}`),
}

/** 活动图片的鉴权读取地址（需登录态，经 useAuthedImage 取 blob）。 */
export function activityImageUrl(imageId: number, size: 'thumb' | 'full' = 'full'): string {
  return `/records/activities/images/${imageId}?size=${size}`
}

export const tasksApi = {
  list: (params?: { status?: TaskStatus }) =>
    api.get<TaskOut[]>(withQuery('/records/tasks', { status: params?.status })),
  create: (data: TaskCreate) => api.post<TaskOut>('/records/tasks', data),
  update: (id: number, data: TaskUpdate) => api.patch<TaskOut>(`/records/tasks/${id}`, data),
  remove: (id: number) => api.delete<void>(`/records/tasks/${id}`),
}

/** 备注接口：列表按联系人取全量（个人量级，无分页），写操作与任务同构。 */
export const notesApi = {
  list: (contactId: number) =>
    api.get<NoteOut[]>(withQuery('/records/notes', { contact_id: contactId })),
  create: (data: NoteCreate) => api.post<NoteOut>('/records/notes', data),
  update: (id: number, data: NoteUpdate) => api.patch<NoteOut>(`/records/notes/${id}`, data),
  remove: (id: number) => api.delete<void>(`/records/notes/${id}`),
}
