/** 表单归一测试：清空外键必须产出 null，否则 PATCH 语义下会变成静默无效。 */
import { describe, expect, it } from 'vitest'
import { clearableId } from '@/utils/form'

describe('clearableId', () => {
  it('Element Plus 清空后的 undefined 归一为 null', () => {
    // el-select 的 valueOnClear 默认是 undefined，而 JSON.stringify 会丢掉值为
    // undefined 的键；后端 PATCH 用 exclude_unset —— 键缺失 = 不改这个字段。
    expect(clearableId(undefined)).toBe(null)
  })

  it('已经是 null 的保持 null', () => {
    expect(clearableId(null)).toBe(null)
  })

  it('有值时原样返回', () => {
    expect(clearableId(7)).toBe(7)
  })

  it('归一后的结果能被 JSON 保留下来（这才是清空生效的关键）', () => {
    expect(JSON.stringify({ contact_id: clearableId(undefined) })).toBe('{"contact_id":null}')
  })
})
