/** 设置页「外部接入（MCP 令牌）」区块测试：列表、签发一次性明文、吊销。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { list, issue, revoke } = vi.hoisted(() => ({
  list: vi.fn(),
  issue: vi.fn(),
  revoke: vi.fn(),
}))
vi.mock('@/api/auth', () => ({ tokensApi: { list, issue, revoke } }))

/** 页面其余区块的依赖：本测试只关心令牌区块，其余一律给空数据。 */
vi.mock('@/api/ai', () => ({
  settingsApi: {
    aiConfig: vi.fn().mockResolvedValue({ configured: false }),
    embeddingConfig: vi.fn().mockResolvedValue({ configured: false }),
    amapConfig: vi.fn().mockResolvedValue({ configured: false }),
  },
  embeddingsApi: { rebuild: vi.fn() },
}))
vi.mock('@/api/contacts', () => ({ contactsApi: { list: vi.fn().mockResolvedValue([]) } }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ user: { contact_id: null }, bindContact: vi.fn() }),
}))

import SettingsPage from '@/pages/SettingsPage.vue'

const MOUNT_OPTIONS = { global: { plugins: [ElementPlus] } }

const TOKEN = {
  id: 3,
  name: 'Claude Desktop',
  created_at: '2026-09-29T10:00:00Z',
  last_used_at: null,
}

describe('设置页 · MCP 令牌', () => {
  beforeEach(() => {
    list.mockReset()
    issue.mockReset()
    revoke.mockReset()
    list.mockResolvedValue([TOKEN])
  })

  it('列出令牌与最后使用时间', async () => {
    const wrapper = mount(SettingsPage, MOUNT_OPTIONS)
    await flushPromises()

    expect(wrapper.text()).toContain('外部接入（MCP 令牌）')
    expect(wrapper.text()).toContain('Claude Desktop')
    expect(wrapper.text()).toContain('未使用')
  })

  it('没有令牌时给出空态', async () => {
    list.mockResolvedValue([])
    const wrapper = mount(SettingsPage, MOUNT_OPTIONS)
    await flushPromises()

    expect(wrapper.text()).toContain('还没有令牌')
  })

  it('签发后弹出一次性明文，并刷新列表', async () => {
    issue.mockResolvedValue({ ...TOKEN, id: 4, token: 'crm_plaintext_once' })
    const wrapper = mount(SettingsPage, MOUNT_OPTIONS)
    await flushPromises()

    await wrapper.get('[data-test="token-name"]').setValue('手机快捷指令')
    await wrapper.get('[data-test="issue-token"]').trigger('click')
    await flushPromises()

    expect(issue).toHaveBeenCalledWith({ name: '手机快捷指令' })
    expect(wrapper.find('[data-test="issued-token"]').exists()).toBe(true)
    expect((wrapper.get('[data-test="issued-token"]').element as HTMLInputElement).value).toBe(
      'crm_plaintext_once',
    )
    expect(list).toHaveBeenCalledTimes(2) // 初次载入 + 签发后刷新
  })

  it('吊销走确认后调用接口并刷新', async () => {
    revoke.mockResolvedValue(undefined)
    const wrapper = mount(SettingsPage, MOUNT_OPTIONS)
    await flushPromises()

    wrapper.findComponent({ name: 'ElPopconfirm' }).vm.$emit('confirm')
    await flushPromises()

    expect(revoke).toHaveBeenCalledWith(TOKEN.id)
    expect(list).toHaveBeenCalledTimes(2)
  })
})
