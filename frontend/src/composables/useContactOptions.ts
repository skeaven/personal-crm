/** 联系人选项 composable：管理页参与者/关联对象下拉的共用数据源。 */
import { ref } from 'vue'
import { contactsApi } from '@/api/contacts'
import type { ContactOut } from '@/api/types'

export interface ContactOption {
  label: string
  value: number
}

/** 加载可读联系人并转换为 el-select 选项；多页共用一份加载逻辑。 */
export function useContactOptions() {
  const options = ref<ContactOption[]>([])
  const contacts = ref<ContactOut[]>([])

  /** 拉取名册并生成选项（display_name 由服务端统一计算）。 */
  async function load(): Promise<void> {
    contacts.value = await contactsApi.list()
    options.value = contacts.value.map((contact) => ({
      label: contact.display_name,
      value: contact.id,
    }))
  }

  /** 按 id 取展示名（表格列渲染用，避免再发请求）。 */
  function nameOf(contactId: number | null): string {
    if (contactId === null) return '—'
    return contacts.value.find((contact) => contact.id === contactId)?.display_name ?? `#${contactId}`
  }

  return { options, contacts, load, nameOf }
}
