/** 日期时间工具：本地时区的展示与提交格式转换。 */

/** 时间戳 → 本地日期字符串 YYYY-MM-DD。
 * 不用 toISOString()：它按 UTC 取日期，东八区的本地零点会倒退一天。 */
export function toDateInput(timestamp: number): string {
  const value = new Date(timestamp)
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${value.getFullYear()}-${month}-${day}`
}
