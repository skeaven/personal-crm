/** 会话列表交互测试。 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import SessionList from '@/components/SessionList.vue'
import type { AiSessionOut } from '@/api/types'

/** 该组件用到 el-button / el-popconfirm，挂载时必须注册组件库，否则渲染不出来。 */
const MOUNT_OPTIONS = { global: { plugins: [ElementPlus] } }

const SESSIONS: AiSessionOut[] = [
  { session_id: 'a', title: '老爸最近怎么样', created_at: '2026-09-27T10:00:00Z', updated_at: '2026-09-27T12:00:00Z' },
  { session_id: 'b', title: '记一笔待办', created_at: '2026-09-26T10:00:00Z', updated_at: '2026-09-26T10:00:00Z' },
]

describe('SessionList', () => {
  it('渲染会话标题', () => {
    const wrapper = mount(SessionList, { props: { sessions: SESSIONS, activeId: null }, ...MOUNT_OPTIONS })

    expect(wrapper.text()).toContain('老爸最近怎么样')
    expect(wrapper.text()).toContain('记一笔待办')
  })

  it('点某条会话抛出 select 事件', async () => {
    const wrapper = mount(SessionList, { props: { sessions: SESSIONS, activeId: null }, ...MOUNT_OPTIONS })

    await wrapper.findAll('[data-test="session-item"]')[1].trigger('click')

    expect(wrapper.emitted('select')?.[0]).toEqual(['b'])
  })

  it('当前会话有选中态', () => {
    const wrapper = mount(SessionList, { props: { sessions: SESSIONS, activeId: 'a' }, ...MOUNT_OPTIONS })

    expect(wrapper.findAll('[data-test="session-item"]')[0].classes()).toContain('active')
    expect(wrapper.findAll('[data-test="session-item"]')[1].classes()).not.toContain('active')
  })

  it('点新建抛出 create 事件', async () => {
    const wrapper = mount(SessionList, { props: { sessions: [], activeId: null }, ...MOUNT_OPTIONS })

    await wrapper.find('[data-test="new-session"]').trigger('click')

    expect(wrapper.emitted('create')).toBeTruthy()
  })
})