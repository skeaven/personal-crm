/** 提醒未读徽标：提醒页标记已读/扫描后，导航徽标必须立即同步（不等 60s 轮询）。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

const { remindersList, unreadCount, markRead, markAllRead, scan, push } = vi.hoisted(() => ({
  remindersList: vi.fn(),
  unreadCount: vi.fn(),
  markRead: vi.fn(),
  markAllRead: vi.fn(),
  scan: vi.fn(),
  push: vi.fn(),
}))
vi.mock('@/api/reminders', () => ({
  remindersApi: { list: remindersList, unreadCount, markRead, markAllRead, scan },
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))

import RemindersPage from '@/pages/RemindersPage.vue'
import { useUnreadReminders } from '@/composables/useUnreadReminders'
import { useAuthStore } from '@/stores/auth'
import type { ReminderOut } from '@/api/types'

const MOUNT_OPTIONS = { global: { plugins: [ElementPlus] } }

/** 一条未读提醒（三源里的任务源）。 */
const UNREAD: ReminderOut = {
  id: 7,
  source: 'task',
  ref_id: 10,
  due_date: '2026-10-06',
  days_left: 0,
  title: '任务：给老爸准备生日礼物（今天到期）',
  contact_id: 29,
  read_at: null,
  created_at: '2026-09-30T04:17:07.278876Z',
}

/** 按文案取按钮：el-table 单元格里的操作按钮没有 data-test，只能按文本定位。 */
function buttonByText(wrapper: VueWrapper, label: string) {
  return wrapper.findAll('button').find((b) => b.text() === label)
}

describe('提醒未读徽标', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // happy-dom 不把 localStorage 提升为全局，而 auth store 初始化要读它
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => {}, removeItem: () => {} })
    setActivePinia(createPinia())
    useAuthStore().token = 'test-token' // isLoggedIn 才有取数资格
  })

  it('refreshUnreadCount 把后端未读数写入共享状态', async () => {
    unreadCount.mockResolvedValue(3)
    const { unreadCount: shared, refreshUnreadCount } = useUnreadReminders()

    await refreshUnreadCount()

    expect(shared.value).toBe(3)
  })

  it('未登录时不取数（保持原值）', async () => {
    useAuthStore().token = ''
    unreadCount.mockResolvedValue(3)
    const { unreadCount: shared, refreshUnreadCount } = useUnreadReminders()
    const before = shared.value

    await refreshUnreadCount()

    expect(unreadCount).not.toHaveBeenCalled()
    expect(shared.value).toBe(before)
  })

  it('提醒页点「已读」后徽标立即同步，不等 60s 轮询', async () => {
    remindersList.mockResolvedValue([{ ...UNREAD }])
    unreadCount.mockResolvedValueOnce(1) // 徽标初值
    const { unreadCount: shared, refreshUnreadCount } = useUnreadReminders()
    await refreshUnreadCount()
    expect(shared.value).toBe(1)

    markRead.mockResolvedValue(undefined)
    unreadCount.mockResolvedValueOnce(0) // 标记已读后后端的新值
    const wrapper = mount(RemindersPage, MOUNT_OPTIONS)
    await flushPromises()

    await buttonByText(wrapper, '已读')?.trigger('click')
    await flushPromises()

    expect(markRead).toHaveBeenCalledWith(7)
    expect(shared.value).toBe(0)
  })

  it('「全部已读」后徽标立即归零', async () => {
    remindersList.mockResolvedValue([{ ...UNREAD }])
    unreadCount.mockResolvedValueOnce(1)
    const { unreadCount: shared, refreshUnreadCount } = useUnreadReminders()
    await refreshUnreadCount()

    markAllRead.mockResolvedValue(1)
    unreadCount.mockResolvedValueOnce(0)
    // 挂载时仍有未读行（否则「全部已读」按钮 disabled），点击后列表清空
    remindersList.mockResolvedValueOnce([{ ...UNREAD }]).mockResolvedValue([])
    const wrapper = mount(RemindersPage, MOUNT_OPTIONS)
    await flushPromises()

    await buttonByText(wrapper, '全部已读')?.trigger('click')
    await flushPromises()

    expect(shared.value).toBe(0)
  })
})
