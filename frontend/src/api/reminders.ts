/** reminders 模块 API 封装：应用内提醒（D22）。 */
import { api } from './client'
import type { ReminderOut, ReminderScanOut } from './types'

export const remindersApi = {
  /** 提醒列表（unreadOnly=true 只看未读；未读在前）。 */
  list: (unreadOnly = false) =>
    api.get<ReminderOut[]>(`/reminders${unreadOnly ? '?unread_only=true' : ''}`),
  /** 未读数（铃铛徽标）。 */
  unreadCount: () => api.get<number>('/reminders/unread-count'),
  /** 单条已读。 */
  markRead: (id: number) => api.post<void>(`/reminders/${id}/read`),
  /** 全部已读；返回影响条数。 */
  markAllRead: () => api.post<number>('/reminders/read-all'),
  /** 手动扫描（幂等）。 */
  scan: () => api.post<ReminderScanOut>('/reminders/scan'),
}
