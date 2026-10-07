/** Agent 对话组件测试：图片上传预览、发送带图、视觉降级文案、提议渲染。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { chat, pendingList, tools, uploadTemp, approve, reject } = vi.hoisted(() => ({
  chat: vi.fn(),
  pendingList: vi.fn(),
  tools: vi.fn(),
  uploadTemp: vi.fn(),
  approve: vi.fn(),
  reject: vi.fn(),
}))
vi.mock('@/api/ai', () => ({ aiApi: { chat, pendingList, tools, approve, reject } }))
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
  tools.mockReset().mockResolvedValue([])
  uploadTemp.mockReset().mockResolvedValue({ temp_path: 'tmp/9/card.png' })
  approve.mockReset()
  reject.mockReset()
})

/** 面板默认收起（showPending=false），先点「待确认」按钮展开再断言。 */
async function openPending(wrapper: ReturnType<typeof mount>): Promise<void> {
  const toggle = wrapper.findAll('button').find((b) => b.text().includes('待确认'))
  await toggle?.trigger('click')
  await flushPromises()
}

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

  it('只有图片没有文字时也能点发送（后端 message 契约给默认指令兜底）', async () => {
    chat.mockImplementation(async (_t, _s, onEvent) => {
      onEvent({ type: 'start', session_id: 's1' })
      onEvent({ type: 'done' })
    })
    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()

    await pickImage(wrapper)
    await flushPromises()
    // 不输入任何文字，直接点发送
    await wrapper.get('[data-test="send"]').trigger('click')
    await flushPromises()

    expect(chat).toHaveBeenCalledWith('帮我看看这张图', 's1', expect.any(Function), ['tmp/9/card.png'])
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
  it('create_contact 提议用中文标签渲染（层级转译为直接/边缘）', async () => {
    // 工具中文名改由 /ai/tools 下发（前端不再硬编码），断言前须把标签喂给组件。
    tools.mockResolvedValue([
      { name: 'create_contact', label: '建联系人', description: '', risk: 'write_queue' },
    ])
    pendingList.mockResolvedValue([
      {
        id: 1,
        tool_name: 'create_contact',
        payload: { tier: 'direct', name: '王', nickname: '王姨', phone: '13800000000' },
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
    expect(text).toContain('姓名: 王')
    expect(text).toContain('昵称: 王姨')
    expect(text).toContain('电话: 13800000000')
    expect(text).not.toContain('phone:')
  })

  it('其他工具提议维持键值拼写，工具名走中文映射', async () => {
    tools.mockResolvedValue([
      { name: 'create_task', label: '建待办', description: '', risk: 'write_queue' },
    ])
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

  it('工具名用 /ai/tools 下发的中文标签渲染', async () => {
    tools.mockResolvedValue([
      { name: 'update_contact', label: '改联系人', description: '', risk: 'write_queue' },
    ])
    pendingList.mockResolvedValue([
      {
        id: 5,
        tool_name: 'update_contact',
        payload: { contact_id: 39, phone: '139' },
        status: 'pending',
        result: null,
        created_at: '2026-10-06T00:00:00Z',
      },
    ])

    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()
    await openPending(wrapper)

    expect(wrapper.get('.pending-item').text()).toContain('改联系人')
  })

  it('标签接口失败时回退工具原名，面板仍可用', async () => {
    tools.mockRejectedValue(new Error('boom'))
    pendingList.mockResolvedValue([
      {
        id: 6,
        tool_name: 'delete_contact',
        payload: { contact_id: 39 },
        status: 'pending',
        result: null,
        created_at: '2026-10-06T00:00:00Z',
      },
    ])

    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()
    await openPending(wrapper)

    expect(wrapper.get('.pending-item').text()).toContain('delete_contact')
  })
})

describe('AgentChat 确认面板渲染与批量', () => {
  const action = (over: Partial<Record<string, unknown>> = {}) => ({
    id: 1,
    tool_name: 'update_contact',
    payload: { contact_id: 39, phone: '139' },
    preview: null,
    status: 'pending',
    result: null,
    created_at: '2026-10-06T00:00:00Z',
    ...over,
  })

  it('update 提议按 preview 显示字段级「原值 → 新值」', async () => {
    pendingList.mockResolvedValue([
      action({ preview: { before: { phone: '138' } } }),
    ])

    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()
    await openPending(wrapper)

    // phone 经 CONTACT_FIELD_LABELS 映射为「电话」——面板是给人看的，不是给字段名看的
    expect(wrapper.get('.pending-item').text()).toContain('电话: 138 → 139')
  })

  it('归档提议（delete_contact）显示「将归档」——软删可恢复，文案须与工具名一致', async () => {
    pendingList.mockResolvedValue([
      action({
        tool_name: 'delete_contact',
        payload: { contact_id: 39 },
        preview: { kind: 'delete', summary: '唐琴（id=39）' },
      }),
    ])

    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()
    await openPending(wrapper)

    expect(wrapper.get('.pending-item').text()).toContain('将归档：唐琴（id=39）')
  })

  it('删重要日期提议显示「将删除」——它是真删，与归档不同', async () => {
    pendingList.mockResolvedValue([
      action({
        tool_name: 'delete_important_date',
        payload: { contact_id: 39, date_id: 7 },
        preview: { kind: 'delete', summary: '唐琴 的 birthday 1990-03-05' },
      }),
    ])

    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()
    await openPending(wrapper)

    expect(wrapper.get('.pending-item').text()).toContain('将删除：唐琴 的 birthday 1990-03-05')
  })

  it('promote 提议不带「将删除」前缀：面板按 kind 判别，不按有没有 summary', async () => {
    pendingList.mockResolvedValue([
      action({
        tool_name: 'promote_contact',
        payload: { contact_id: 34 },
        preview: { kind: 'promote', summary: '王芳（id=34）升级为直接联系人' },
      }),
    ])

    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()
    await openPending(wrapper)

    const text = wrapper.get('.pending-item').text()
    expect(text).not.toContain('将删除')
    expect(text).toContain('升级为直接联系人')
  })

  it('未知 kind 不加前缀：将来新增 preview 语义不会被误标成删除', async () => {
    pendingList.mockResolvedValue([
      action({
        tool_name: 'some_future_tool',
        payload: { id: 1 },
        preview: { kind: 'merge', summary: '合并两条记录' },
      }),
    ])

    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()
    await openPending(wrapper)

    const text = wrapper.get('.pending-item').text()
    expect(text).not.toContain('将删除')
    expect(text).toContain('合并两条记录')
  })

  it('重要日期字段用中文名渲染，不暴露英文键', async () => {
    pendingList.mockResolvedValue([
      action({
        tool_name: 'update_important_date',
        payload: { contact_id: 39, date_id: 7, date_solar: '1991-04-06' },
        preview: { before: { date_solar: '1990-03-05' } },
      }),
    ])

    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()
    await openPending(wrapper)

    expect(wrapper.get('.pending-item').text()).toContain('公历日期: 1990-03-05 → 1991-04-06')
  })

  it('勾选多条后批量确认：逐条 approve，逐条记结果，不整体回滚', async () => {
    pendingList.mockResolvedValue([action({ id: 1 }), action({ id: 2 })])
    approve
      .mockResolvedValueOnce({ ...action({ id: 1 }), result: { ok: true, message: '已改' } })
      .mockResolvedValueOnce({ ...action({ id: 2 }), result: { ok: false, error: '联系人不存在' } })

    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()
    await openPending(wrapper)

    const boxes = wrapper.findAll('.pending-item input[type="checkbox"]')
    await boxes[0].setValue(true)
    await boxes[1].setValue(true)
    await wrapper.get('[data-test="batch-approve"]').trigger('click')
    await flushPromises()

    expect(approve).toHaveBeenCalledTimes(2)
    expect(approve).toHaveBeenNthCalledWith(1, 1)
    expect(approve).toHaveBeenNthCalledWith(2, 2)
    const text = wrapper.text()
    expect(text).toContain('已改')
    expect(text).toContain('联系人不存在')
  })

  it('批量执行期间单条确认/拒绝按钮禁用：避免同一条被重复提交两次', async () => {
    // approve 悬而不决，把组件钉在"批量进行中"的状态上再断言按钮态
    let release: () => void = () => {}
    approve.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = () => resolve({ ...action({ id: 1 }), result: { ok: true, message: '已改' } })
        }),
    )
    pendingList.mockResolvedValue([action({ id: 1 })])

    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()
    await openPending(wrapper)

    const box = wrapper.find('.pending-item input[type="checkbox"]')
    await box.setValue(true)
    await wrapper.get('[data-test="batch-approve"]').trigger('click')
    await flushPromises()

    const itemButtons = wrapper.get('.pending-item').findAll('button')
    expect(itemButtons.length).toBeGreaterThan(0)
    expect(itemButtons.every((b) => b.attributes('disabled') !== undefined)).toBe(true)

    release() // 收尾，避免游离 Promise 影响后续用例
    await flushPromises()
  })
})
