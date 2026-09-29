/** 搜索页测试：取数、空态、未配置降级、点击跳转。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { search, push } = vi.hoisted(() => ({ search: vi.fn(), push: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/api/ai', () => ({ searchApi: { search } }))

import SearchPage from '@/pages/SearchPage.vue'
import { ApiError } from '@/api/client'

const MOUNT_OPTIONS = { global: { plugins: [ElementPlus] } }

/** 输入关键词并回车（语义搜索按次调用 embedding，不做输入即搜）。 */
async function submit(wrapper: ReturnType<typeof mount>, keyword: string): Promise<void> {
  await wrapper.get('[data-test="search-input"] input').setValue(keyword)
  await wrapper.get('[data-test="search-input"] input').trigger('keyup.enter')
  await flushPromises()
}

describe('SearchPage', () => {
  beforeEach(() => {
    search.mockReset()
    push.mockReset()
  })

  it('命中结果：按分组渲染，点联系人跳详情页', async () => {
    search.mockResolvedValue([
      { entity_type: 'contact', entity_id: 7, content: '王姨 退休教师', distance: 0.2 },
    ])
    const wrapper = mount(SearchPage, MOUNT_OPTIONS)

    await submit(wrapper, '爱养花的人')
    await wrapper.get('[data-test="search-item"][data-type="contact"]').trigger('click')

    expect(search).toHaveBeenCalledWith('爱养花的人')
    expect(wrapper.text()).toContain('王姨 退休教师')
    expect(push).toHaveBeenCalledWith('/contacts/7')
  })

  it('无结果时提示索引可能未建（语义索引要手动重建）', async () => {
    search.mockResolvedValue([])
    const wrapper = mount(SearchPage, MOUNT_OPTIONS)

    await submit(wrapper, '不存在的东西')

    expect(wrapper.text()).toContain('没有找到')
    expect(wrapper.text()).toContain('重建')
  })

  it('未配置 Embedding：透传后端提示并给出去设置页的入口', async () => {
    search.mockRejectedValue(new ApiError('尚未配置 Embedding 模型，请先在设置页完成配置', 400))
    const wrapper = mount(SearchPage, MOUNT_OPTIONS)

    await submit(wrapper, '随便搜点什么')

    expect(wrapper.text()).toContain('尚未配置 Embedding 模型')
    await wrapper.get('[data-test="goto-settings"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/settings')
  })

  it('未搜索时不渲染空态（避免一进页面就说「没有找到」）', () => {
    const wrapper = mount(SearchPage, MOUNT_OPTIONS)

    expect(wrapper.text()).not.toContain('没有找到')
    expect(search).not.toHaveBeenCalled()
  })
})
