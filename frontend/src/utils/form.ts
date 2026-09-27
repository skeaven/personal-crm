/**
 * 表单提交前的取值归一。
 *
 * Element Plus 的 el-select 清空产出的是 undefined（`valueOnClear` 默认为 void 0），
 * 而 JSON.stringify 会丢掉值为 undefined 的键；后端 PATCH 是 exclude_unset 语义——
 * 键缺失等于「不改这个字段」。于是「清空对象」会变成静默无效：前端提示保存成功，
 * 对象却还在。清空外键必须显式给 null 才真的清得掉。
 *
 * 注意 el-date-picker 清空产出的是 null，不需要经过这里。
 */
export function clearableId(value: number | null | undefined): number | null {
  return value ?? null
}
