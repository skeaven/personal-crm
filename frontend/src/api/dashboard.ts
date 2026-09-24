/** dashboard 模块 API 封装：待办/统计/时间线，对应 backend dashboard/api.py */
import { api } from './client'
import type { DashboardStatsOut, TimelineOut, TodoBucket, TodoItemOut } from './types'

export const dashboardApi = {
  /** 待办看板：五来源统一视图，bucket 取 todo/overdue/done/all。 */
  todos: (bucket: TodoBucket) => api.get<TodoItemOut[]>(`/dashboard/todos?bucket=${bucket}`),
  /** 主页统计卡（口径与名册 ?activity= 过滤联动）。 */
  stats: () => api.get<DashboardStatsOut>('/dashboard/stats'),
  /** 联系人时间线：三源全量倒序（后端聚合，前端切片渲染）。 */
  timeline: (contactId: number) =>
    api.get<TimelineOut>(`/contacts/${contactId}/timeline`),
}
