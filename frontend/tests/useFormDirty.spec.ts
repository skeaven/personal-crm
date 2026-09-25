/** 脏检查测试：保存按钮的行为契约（用户 2026-09-25 指令）。 */
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { useFormDirty } from '@/composables/useFormDirty'

describe('useFormDirty', () => {
  it('刚打开时无改动，保存不可点', () => {
    const form = ref({ title: '原标题', amount: '100' })
    const dirty = useFormDirty(form)

    dirty.capture()

    expect(dirty.isDirty.value).toBe(false)
    expect(dirty.canSubmit.value).toBe(false)
  })

  it('改了内容就可保存', () => {
    const form = ref({ title: '原标题' })
    const dirty = useFormDirty(form)
    dirty.capture()

    form.value.title = '新标题'

    expect(dirty.isDirty.value).toBe(true)
    expect(dirty.canSubmit.value).toBe(true)
  })

  it('改完又改回原值，保存重新变灰', () => {
    const form = ref({ title: '原标题' })
    const dirty = useFormDirty(form)
    dirty.capture()

    form.value.title = '改了'
    form.value.title = '原标题'

    expect(dirty.canSubmit.value).toBe(false)
  })

  it('有改动但必填项为空时仍然不可保存', () => {
    const form = ref({ title: '原标题' })
    const dirty = useFormDirty(form, {
      isSubmittable: (value) => value.title.trim().length > 0,
    })
    dirty.capture()

    form.value.title = '   '

    expect(dirty.isDirty.value).toBe(true)
    expect(dirty.canSubmit.value).toBe(false)
  })

  it('新建态（空表单为基线）：填了必填项才可保存', () => {
    const form = ref({ title: '' })
    const dirty = useFormDirty(form, {
      isSubmittable: (value) => value.title.trim().length > 0,
    })
    dirty.capture()

    expect(dirty.canSubmit.value).toBe(false)

    form.value.title = '家庭聚餐'

    expect(dirty.canSubmit.value).toBe(true)
  })

  it('数组增删算改动', () => {
    const form = ref({ ids: [1, 2] })
    const dirty = useFormDirty(form)
    dirty.capture()

    form.value.ids.push(3)
    expect(dirty.isDirty.value).toBe(true)

    form.value.ids.pop()
    expect(dirty.isDirty.value).toBe(false)
  })

  it('对象 key 顺序不同但内容相同不算改动', () => {
    const form = ref<Record<string, unknown>>({ alpha: 1, beta: 2 })
    const dirty = useFormDirty(form)
    dirty.capture()

    form.value = { beta: 2, alpha: 1 }

    expect(dirty.isDirty.value).toBe(false)
  })
})
