<script setup lang="ts">
/**
 * 资金表单弹窗（D16 居中弹窗）：列表页与联系人往来 Tab 共用同一组件。
 * 保存按钮走 useFormDirty 置灰策略；取消/关闭不落库。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { fundsApi } from '@/api/funds'
import { ApiError } from '@/api/client'
import { useContactOptions } from '@/composables/useContactOptions'
import { useFormDirty } from '@/composables/useFormDirty'
import type { FundCategory, FundDirection, FundFlowOut } from '@/api/types'

const props = defineProps<{
  visible: boolean
  flow: FundFlowOut | null
  presetContactId?: number
}>()
const emit = defineEmits<{ 'update:visible': [value: boolean]; saved: [] }>()

const { options, load: loadContacts } = useContactOptions()
const saving = ref(false)

interface FundDraft {
  direction: FundDirection
  category: FundCategory
  contact_id: number | null
  amount: string
  occurred_at: string
  due_at: string | null
  description: string
}

/** 空表单：发生日默认今天（最常见的录入场景）。 */
function emptyDraft(): FundDraft {
  return {
    direction: 'out',
    category: 'loan',
    contact_id: props.presetContactId ?? null,
    amount: '',
    occurred_at: new Date().toISOString().slice(0, 10),
    due_at: null,
    description: '',
  }
}

const form = ref<FundDraft>(emptyDraft())
const { capture, canSubmit } = useFormDirty(form, {
  isSubmittable: (draft) => draft.amount.trim().length > 0 && !!draft.occurred_at,
})

const dialogTitle = computed(() => (props.flow ? '编辑记录' : '记一笔资金往来'))

watch(
  () => props.visible,
  async (opened) => {
    if (!opened) return
    await loadContacts()
    const source = props.flow
    form.value = source
      ? {
          direction: source.direction,
          category: source.category,
          contact_id: source.contact_id,
          amount: source.amount,
          occurred_at: source.occurred_at,
          due_at: source.due_at,
          description: source.description ?? '',
        }
      : emptyDraft()
    capture()
  },
  { immediate: true },
)

/** 提交：金额与发生日必填（由 canSubmit 保证非空）。 */
async function submit(): Promise<void> {
  saving.value = true
  try {
    const payload = {
      direction: form.value.direction,
      category: form.value.category,
      contact_id: form.value.contact_id,
      amount: form.value.amount,
      occurred_at: form.value.occurred_at,
      due_at: form.value.due_at,
      description: form.value.description || null,
    }
    if (props.flow) {
      await fundsApi.update(props.flow.id, payload)
      ElMessage.success('资金记录已更新')
    } else {
      await fundsApi.create(payload)
      ElMessage.success('资金记录已记下')
    }
    emit('saved')
    emit('update:visible', false)
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="dialogTitle"
    width="480px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <el-form label-position="top">
      <el-form-item label="方向">
        <el-radio-group v-model="form.direction">
          <el-radio-button value="out">流出（借出/支出）</el-radio-button>
          <el-radio-button value="in">流入（借入/收到）</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="类别">
        <el-radio-group v-model="form.category">
          <el-radio-button value="loan">借款</el-radio-button>
          <el-radio-button value="repayment">还款</el-radio-button>
          <el-radio-button value="gift_money">礼金</el-radio-button>
          <el-radio-button value="other">其他</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="对象联系人">
        <el-select v-model="form.contact_id" filterable clearable placeholder="选填">
          <el-option v-for="opt in options" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="金额（元）" required>
        <el-input v-model="form.amount" placeholder="如 2000.00" />
      </el-form-item>
      <el-form-item label="发生日期" required>
        <el-date-picker
          v-model="form.occurred_at"
          type="date"
          value-format="YYYY-MM-DD"
          class="full"
        />
      </el-form-item>
      <el-form-item label="应收/应还日（借贷类填写后自动进入未结清）">
        <el-date-picker
          v-model="form.due_at"
          type="date"
          value-format="YYYY-MM-DD"
          clearable
          class="full"
        />
      </el-form-item>
      <el-form-item label="说明">
        <el-input v-model="form.description" type="textarea" :rows="2" placeholder="选填" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button text @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="!canSubmit" @click="submit">
        保存
      </el-button>
    </template>
  </el-dialog>
</template>
