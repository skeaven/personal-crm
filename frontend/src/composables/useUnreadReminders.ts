/** 提醒未读数：导航徽标与提醒页共享的单一来源。
 *
 * 提醒页标记已读/扫描后调 refreshUnreadCount，徽标当场同步——否则只能等
 * 布局里 60s 一次的轮询，用户刚清完提醒却仍看到徽标挂着数字。
 */
import { ref, type Ref } from 'vue'
import { remindersApi } from '@/api/reminders'
import { useAuthStore } from '@/stores/auth'

/** 模块级单例：所有调用方（布局、提醒页）看到同一个计数。 */
const unreadCount = ref(0)

/** 拉取最新未读数；未登录不请求，失败静默保持原值（下一轮再取）。 */
async function refreshUnreadCount(): Promise<void> {
  if (!useAuthStore().isLoggedIn) return
  try {
    unreadCount.value = await remindersApi.unreadCount()
  } catch {
    /* 轮询失败静默，下轮再取 */
  }
}

/** 供布局订阅计数、供提醒页在改写后主动同步。 */
export function useUnreadReminders(): {
  unreadCount: Ref<number>
  refreshUnreadCount: () => Promise<void>
} {
  return { unreadCount, refreshUnreadCount }
}
