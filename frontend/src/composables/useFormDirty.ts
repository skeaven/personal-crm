/**
 * 表单脏检查（全站唯一实现点）：
 * 只有「相对打开时的快照有改动」且「附加校验通过」才允许保存。
 *
 * 目的是防误操作——用户改完表单直接关闭不落库，只有真的改了并点保存才写入。
 * 新建场景把空表单当基线，因此「填了必填项」天然等于「有改动」，无需分支处理。
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'

interface FormDirtyOptions<T> {
  /** 附加可用性校验（如必填项非空）；返回 false 时即便有改动也不可保存。 */
  isSubmittable?: (value: T) => boolean
}

interface FormDirty<T> {
  /** 把当前值记为基线；打开弹窗/载入数据后调用。 */
  capture: () => void
  /** 相对基线是否有改动。 */
  isDirty: ComputedRef<boolean>
  /** 保存按钮是否可用。 */
  canSubmit: ComputedRef<boolean>
}

/**
 * 稳定序列化：对象按 key 排序后再序列化。
 * 否则 `{a:1,b:2}` 与 `{b:2,a:1}` 会被判成有改动（表单回填时重建对象很常见）。
 */
function stableSerialize(value: unknown): string {
  return JSON.stringify(value, (_key, val: unknown) => {
    if (val && typeof val === 'object' && !Array.isArray(val)) {
      return Object.fromEntries(
        Object.entries(val as Record<string, unknown>).sort(([left], [right]) =>
          left.localeCompare(right),
        ),
      )
    }
    return val
  })
}

export function useFormDirty<T>(current: Ref<T>, options: FormDirtyOptions<T> = {}): FormDirty<T> {
  const baseline = ref<string>('')

  /** 记录基线快照。 */
  function capture(): void {
    baseline.value = stableSerialize(current.value)
  }

  const isDirty = computed(() => stableSerialize(current.value) !== baseline.value)

  const canSubmit = computed(
    () => isDirty.value && (options.isSubmittable?.(current.value) ?? true),
  )

  return { capture, isDirty, canSubmit }
}
