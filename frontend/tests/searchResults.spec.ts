/** 语义搜索结果展示测试：分组顺序、可点性、未知类型兜底。 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import SearchResults from '@/components/SearchResults.vue'
import type { SearchItemOut } from '@/api/types'

const MOUNT_OPTIONS = { global: { plugins: [ElementPlus] } }

/** 故意打乱后端顺序：分组要按固定类型顺序排，而不是照抄返回顺序。 */
const ITEMS: SearchItemOut[] = [
  { entity_type: 'note', entity_id: 11, content: '搬家那天他们来帮了忙', distance: 0.41 },
  { entity_type: 'contact', entity_id: 7, content: '王姨 退休教师 爱养花', distance: 0.21 },
  { entity_type: 'gift', entity_id: 3, content: '送 王姨 白酒', distance: 0.33 },
]

describe('SearchResults', () => {
  it('按固定类型顺序分组并显示中文标签', () => {
    const wrapper = mount(SearchResults, { props: { items: ITEMS }, ...MOUNT_OPTIONS })

    const groups = wrapper.findAll('[data-test="search-group"]')
    expect(groups.map((g) => g.attributes('data-type'))).toEqual(['contact', 'gift', 'note'])
    expect(wrapper.text()).toContain('联系人')
    expect(wrapper.text()).toContain('礼物')
    expect(wrapper.text()).toContain('备注')
  })

  it('点联系人条目抛出 open 事件', async () => {
    const wrapper = mount(SearchResults, { props: { items: ITEMS }, ...MOUNT_OPTIONS })

    await wrapper.get('[data-test="search-item"][data-type="contact"]').trigger('click')

    expect(wrapper.emitted('open')?.[0]).toEqual([ITEMS[1]])
  })

  it('非联系人条目不可点（这些实体还没有详情页）', async () => {
    const wrapper = mount(SearchResults, { props: { items: ITEMS }, ...MOUNT_OPTIONS })

    await wrapper.get('[data-test="search-item"][data-type="gift"]').trigger('click')

    expect(wrapper.emitted('open')).toBeUndefined()
  })

  it('未知类型兜底显示原始类型名，结果不丢', () => {
    const wrapper = mount(SearchResults, {
      props: { items: [{ entity_type: 'weird', entity_id: 1, content: '新类型的数据', distance: 0.5 }] },
      ...MOUNT_OPTIONS,
    })

    expect(wrapper.text()).toContain('weird')
    expect(wrapper.text()).toContain('新类型的数据')
  })
})
