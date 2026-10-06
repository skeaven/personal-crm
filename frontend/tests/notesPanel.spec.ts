/** 备注面板测试：加载、新增、仅所有者可改删、删除后刷新。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import ElementPlus from 'element-plus'

const { notesList, notesCreate, notesUpdate, notesRemove } = vi.hoisted(() => ({
  notesList: vi.fn(),
  notesCreate: vi.fn(),
  notesUpdate: vi.fn(),
  notesRemove: vi.fn(),
}))
vi.mock('@/api/records', () => ({
  notesApi: {
    list: notesList,
    create: notesCreate,
    update: notesUpdate,
    remove: notesRemove,
  },
}))

import NotesPanel from '@/components/NotesPanel.vue'
import { useAuthStore } from '@/stores/auth'
import type { NoteOut, UserOut } from '@/api/types'

const ME: UserOut = { id: 7, username: 'demo', display_name: '阿澄', family_id: 1, contact_id: null }

const NOTES: NoteOut[] = [
  {
    id: 11,
    contact_id: 1,
    content: '上次聊天提到想换车',
    owner_user_id: 7,
    owner_display_name: '阿澄',
    visibility: 'family',
    created_at: '2026-09-30T10:00:00Z',
    updated_at: '2026-09-30T10:00:00Z',
  },
  {
    id: 12,
    contact_id: 1,
    content: '家人补充的备注',
    owner_user_id: 8,
    owner_display_name: '小佟',
    visibility: 'family',
    created_at: '2026-09-29T10:00:00Z',
    updated_at: '2026-09-29T10:00:00Z',
  },
]

let pinia: Pinia

beforeEach(() => {
  // happy-dom 不把 localStorage 提升为全局，而 auth store 初始化要读它
  vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => {}, removeItem: () => {} })
  notesList.mockReset().mockResolvedValue(NOTES)
  notesCreate.mockReset()
  notesUpdate.mockReset()
  notesRemove.mockReset()
  // 组件与测试共享同一 pinia 实例，auth.user 才能在组件内读到
  pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = ME
})

async function mountPanel(contactId = 1) {
  const wrapper = mount(NotesPanel, {
    props: { contactId },
    global: { plugins: [ElementPlus, pinia] },
    // popconfirm 的 popper teleport 到 document.body，脱离文档挂载会让弹层内容查不到
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

describe('NotesPanel', () => {
  it('挂载即按联系人加载备注并渲染内容与记录人', async () => {
    const wrapper = await mountPanel()

    expect(notesList).toHaveBeenCalledWith(1)
    expect(wrapper.text()).toContain('上次聊天提到想换车')
    expect(wrapper.text()).toContain('阿澄')
    expect(wrapper.text()).toContain('小佟')
  })

  it('输入正文点保存即创建并刷新列表', async () => {
    const wrapper = await mountPanel()
    notesCreate.mockResolvedValue({ ...NOTES[0], id: 13, content: '新备注' })
    notesList.mockResolvedValue([...NOTES, { ...NOTES[0], id: 13, content: '新备注' }])

    await wrapper.get('[data-test="note-input"]').setValue('新备注')
    await wrapper.get('[data-test="note-submit"]').trigger('click')
    await flushPromises()

    expect(notesCreate).toHaveBeenCalledWith({ contact_id: 1, content: '新备注' })
    expect(wrapper.text()).toContain('新备注')
  })

  it('空正文不能提交', async () => {
    const wrapper = await mountPanel()

    await wrapper.get('[data-test="note-submit"]').trigger('click')

    expect(notesCreate).not.toHaveBeenCalled()
  })

  it('只有本人备注有编辑与删除按钮', async () => {
    const wrapper = await mountPanel()

    const items = wrapper.findAll('[data-test="note-item"]')
    expect(items[0].find('[data-test="note-edit"]').exists()).toBe(true)
    expect(items[0].find('[data-test="note-delete"]').exists()).toBe(true)
    expect(items[1].find('[data-test="note-edit"]').exists()).toBe(false)
    expect(items[1].find('[data-test="note-delete"]').exists()).toBe(false)
  })

  it('编辑保存调用更新接口并退出编辑态', async () => {
    const wrapper = await mountPanel()
    notesUpdate.mockResolvedValue({ ...NOTES[0], content: '改过的备注' })
    notesList.mockResolvedValue([{ ...NOTES[0], content: '改过的备注' }, NOTES[1]])

    await wrapper.get('[data-test="note-edit"]').trigger('click')
    const input = wrapper.get('[data-test="note-edit-input"]')
    await input.setValue('改过的备注')
    await wrapper.get('[data-test="note-edit-save"]').trigger('click')
    await flushPromises()

    expect(notesUpdate).toHaveBeenCalledWith(11, { content: '改过的备注' })
    expect(wrapper.text()).toContain('改过的备注')
    expect(wrapper.find('[data-test="note-edit-input"]').exists()).toBe(false)
  })

  it('删除走确认弹层并刷新列表', async () => {
    const wrapper = await mountPanel()
    notesRemove.mockResolvedValue(undefined)

    await wrapper.get('[data-test="note-delete"]').trigger('click')
    await flushPromises()
    // popper 开启是异步的（tooltip 定位后渲染），只 flushPromises 不够
    await new Promise((resolve) => setTimeout(resolve, 50))
    // el-popconfirm 确认按钮 teleport 到 body 的 popper 里（action 区，文案为「删除」）
    const confirm = [...document.querySelectorAll('.el-popconfirm__action .el-button')].find(
      (button) => button.textContent?.includes('删除'),
    ) as HTMLButtonElement | undefined
    expect(confirm).toBeTruthy()
    confirm!.click()
    await flushPromises()

    expect(notesRemove).toHaveBeenCalledWith(11)
    expect(notesList).toHaveBeenCalledTimes(2)
  })
})
