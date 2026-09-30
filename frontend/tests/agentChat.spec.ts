/** Agent 对话组件测试：图片上传预览、发送带图、视觉降级文案、提议渲染。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { chat, pendingList, uploadTemp } = vi.hoisted(() => ({
  chat: vi.fn(),
  pendingList: vi.fn(),
  uploadTemp: vi.fn(),
}))
vi.mock('@/api/ai', () => ({ aiApi: { chat, pendingList } }))
// 保留真实 ApiError（组件用 instanceof 判错），只替换 uploadTemp
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return { ...actual, api: { ...actual.api, uploadTemp } }
})

import AgentChat from '@/components/AgentChat.vue'

const MOUNT_OPTIONS = {
  props: { sessionId: 's1' },
  global: { plugins: [ElementPlus] },
}

beforeEach(() => {
  chat.mockReset()
  pendingList.mockReset().mockResolvedValue([])
  uploadTemp.mockReset().mockResolvedValue({ temp_path: 'tmp/9/card.png' })
})

/** 模拟选择一张图片（jsdom 不能直接赋 files，用 defineProperty）。 */
async function pickImage(wrapper: ReturnType<typeof mount>): Promise<void> {
  const input = wrapper.find('input[type="file"]')
  const file = new File(['x'], 'card.png', { type: 'image/png' })
  Object.defineProperty(input.element, 'files', { value: [file] })
  await input.trigger('change')
}

describe('AgentChat 图片', () => {
  it('选图即传临时区并显示预览', async () => {
    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()

    await pickImage(wrapper)
    await flushPromises()

    expect(uploadTemp).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-test="pending-image"]').exists()).toBe(true)
  })

  it('发送时带图片路径并清空预览，气泡留缩略图', async () => {
    chat.mockImplementation(async (_t, _s, onEvent) => {
      onEvent({ type: 'start', session_id: 's1' })
      onEvent({ type: 'done' })
    })
    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()

    await pickImage(wrapper)
    await wrapper.get('[data-test="chat-input"]').setValue('存下名片')
    await wrapper.get('[data-test="send"]').trigger('click')
    await flushPromises()

    expect(chat).toHaveBeenCalledWith('存下名片', 's1', expect.any(Function), ['tmp/9/card.png'])
    expect(wrapper.find('[data-test="pending-image"]').exists()).toBe(false)
    expect(wrapper.find('.msg-image').exists()).toBe(true)
  })

  it('视觉不支持的错误帧原样显示引导文案', async () => {
    chat.mockImplementation(async (_t, _s, onEvent) => {
      onEvent({ type: 'start', session_id: 's1' })
      onEvent({
        type: 'error',
        code: 'vision_unsupported',
        message:
          '当前模型不支持图片输入，请在设置页换用支持视觉的模型（上游：image input not supported）',
      })
      onEvent({ type: 'done' })
    })
    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()

    await wrapper.get('[data-test="chat-input"]').setValue('存下名片')
    await wrapper.get('[data-test="send"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('不支持图片输入')
    expect(wrapper.text()).toContain('设置页')
  })
})

describe('AgentChat 确认面板', () => {
  /** 面板默认收起（showPending=false），先点「待确认」按钮展开再断言。 */
  async function openPending(wrapper: ReturnType<typeof mount>): Promise<void> {
    const toggle = wrapper.findAll('button').find((b) => b.text().includes('待确认'))
    await toggle?.trigger('click')
    await flushPromises()
  }


  it('create_contact 提议用中文标签渲染（层级转译为直接/边缘）', async () => {
    pendingList.mockResolvedValue([
      {
        id: 1,
        tool_name: 'create_contact',
        payload: { tier: 'direct', last_name: '王', nickname: '王姨', phone: '13800000000' },
        status: 'pending',
        result: null,
        created_at: '2026-09-30T00:00:00Z',
      },
    ])
    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()
    await openPending(wrapper)

    const text = wrapper.get('.pending-item').text()
    expect(text).toContain('建联系人')
    expect(text).toContain('层级: 直接')
    expect(text).toContain('昵称: 王姨')
    expect(text).toContain('电话: 13800000000')
    expect(text).not.toContain('phone:')
  })

  it('其他工具提议维持键值拼写，工具名走中文映射', async () => {
    pendingList.mockResolvedValue([
      {
        id: 2,
        tool_name: 'create_task',
        payload: { title: '给老爸打电话' },
        status: 'pending',
        result: null,
        created_at: '2026-09-30T00:00:00Z',
      },
    ])
    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()
    await openPending(wrapper)

    expect(wrapper.get('.pending-item').text()).toContain('title: 给老爸打电话')
    expect(wrapper.text()).toContain('建待办')
  })
})
