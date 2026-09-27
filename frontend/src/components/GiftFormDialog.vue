<script setup lang="ts">
/**
 * 礼物表单弹窗（D16 居中弹窗）：列表页与联系人往来 Tab 共用同一组件。
 * 保存按钮走 useFormDirty 置灰策略；取消/关闭不落库。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { giftsApi } from '@/api/gifts'
import { ApiError } from '@/api/client'
import { useContactOptions } from '@/composables/useContactOptions'
import { useFormDirty } from '@/composables/useFormDirty'
import { clearableId } from '@/utils/form'
import type { GiftDirection, GiftOut } from '@/api/types'

const props = defineProps<{
  visible: boolean
  gift: GiftOut | null
  presetContactId?: number
}>()
const emit = defineEmits<{ 'update:visible': [value: boolean]; saved: [] }>()

const { options, load: loadContacts } = useContactOptions()
const saving = ref(false)

interface GiftDraft {
  direction: GiftDirection
  title: string
  contact_id: number | null
  occasion: string
  amount: string
  given_at: string | null
  link: string
  description: string
}

/** 空表单：方向默认「我送出」，联系人预选当前联系人（从详情页打开时）。 */
function emptyDraft(): GiftDraft {
  return {
    direction: 'given',
    title: '',
    contact_id: props.presetContactId ?? null,
    occasion: '',
    amount: '',
    given_at: null,
    link: '',
    description: '',
  }
}

const form = ref<GiftDraft>(emptyDraft())
const { capture, canSubmit } = useFormDirty(form, {
  isSubmittable: (draft) => draft.title.trim().length > 0,
})

const dialogTitle = computed(() => (props.gift ? '编辑礼物' : '记一笔礼物'))

watch(
  () => props.visible,
  async (opened) => {
    if (!opened) return
    await loadContacts()
    const source = props.gift
    form.value = source
      ? {
          direction: source.direction,
          title: source.title,
          contact_id: source.contact_id,
          occasion: source.occasion ?? '',
          amount: source.amount ?? '',
          given_at: source.given_at,
          link: source.link ?? '',
          description: source.description ?? '',
        }
      : emptyDraft()
    capture()
  },
  { immediate: true },
)

/** 提交：空字符串转 null，避免把空串写进库。 */
async function submit(): Promise<void> {
  saving.value = true
  try {
    const payload = {
      direction: form.value.direction,
      title: form.value.title,
      contact_id: clearableId(form.value.contact_id),
      occasion: form.value.occasion || null,
      amount: form.value.amount || null,
      given_at: form.value.given_at,
      link: form.value.link || null,
      description: form.value.description || null,
    }
    if (props.gift) {
      await giftsApi.update(props.gift.id, payload)
      ElMessage.success('礼物已更新')
    } else {
      await giftsApi.create(payload)
      ElMessage.success('礼物已记下')
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
          <el-radio-button value="given">我送出</el-radio-button>
          <el-radio-button value="received">我收到</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="礼物名称" required>
        <el-input v-model="form.title" placeholder="如：龙井茶" />
      </el-form-item>
      <el-form-item label="对象">
        <el-select v-model="form.contact_id" filterable clearable placeholder="给谁/谁送的">
          <el-option v-for="opt in options" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="场合">
        <el-input v-model="form.occasion" placeholder="生日、婚礼、探病…（选填）" />
      </el-form-item>
      <el-form-item label="金额（元）">
        <el-input v-model="form.amount" placeholder="选填，如 388.00" />
      </el-form-item>
      <el-form-item label="日期">
        <el-date-picker
          v-model="form.given_at"
          type="date"
          value-format="YYYY-MM-DD"
          clearable
          class="full"
        />
      </el-form-item>
      <el-form-item label="购买/参考链接">
        <el-input v-model="form.link" placeholder="选填" />
      </el-form-item>
      <el-form-item label="礼物说明">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          placeholder="支持 Markdown（选填）"
        />
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
