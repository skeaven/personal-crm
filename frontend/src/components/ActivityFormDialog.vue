<script setup lang="ts">
/**
 * 活动表单弹窗（D16：全站数据录入统一 el-dialog 居中弹窗，不用抽屉）。
 * 列表页「编辑」与详情页「查看详情」复用同一个组件，保证两处行为完全一致。
 * 保存按钮走 useFormDirty：无改动或必填未过一律置灰；取消/关闭不落库。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { activitiesApi } from '@/api/records'
import { ApiError } from '@/api/client'
import { useContactOptions } from '@/composables/useContactOptions'
import { useFormDirty } from '@/composables/useFormDirty'
import ImageUploader from '@/components/ImageUploader.vue'
import type { ActivityOut, ImageRefIn } from '@/api/types'

const props = defineProps<{
  visible: boolean
  activity: ActivityOut | null
  presetContactId?: number
}>()
const emit = defineEmits<{ 'update:visible': [value: boolean]; saved: [] }>()

const { options, load: loadContacts } = useContactOptions()
const saving = ref(false)

interface ActivityDraft {
  title: string
  occurred_at: number | null
  location: string
  detail: string
  participant_ids: number[]
  images: ImageRefIn[]
}

/** 空表单：时间默认当前时刻，省得每次手填；参与者预选当前联系人（从详情页打开时）。 */
function emptyDraft(): ActivityDraft {
  return {
    title: '',
    occurred_at: Date.now(),
    location: '',
    detail: '',
    participant_ids: props.presetContactId ? [props.presetContactId] : [],
    images: [],
  }
}

const form = ref<ActivityDraft>(emptyDraft())
const { capture, canSubmit } = useFormDirty(form, {
  isSubmittable: (draft) => draft.title.trim().length > 0,
})

const dialogTitle = computed(() => (props.activity ? '编辑活动' : '记一次活动'))

watch(
  () => props.visible,
  async (opened) => {
    if (!opened) return
    await loadContacts()
    const source = props.activity
    form.value = source
      ? {
          title: source.title,
          occurred_at: source.occurred_at ? new Date(source.occurred_at).getTime() : null,
          location: source.location ?? '',
          detail: source.detail ?? '',
          participant_ids: [...source.participant_ids],
          images: source.images.map((image) => ({ id: image.id })),
        }
      : emptyDraft()
    capture()
  },
  { immediate: true },
)

/** 提交：时间戳转 ISO，图片按数组顺序全量提交（后端据此重排与删除）。 */
async function submit(): Promise<void> {
  saving.value = true
  try {
    const payload = {
      title: form.value.title,
      occurred_at: form.value.occurred_at ? new Date(form.value.occurred_at).toISOString() : null,
      location: form.value.location || null,
      detail: form.value.detail || null,
      participant_ids: form.value.participant_ids,
      images: form.value.images,
    }
    if (props.activity) {
      await activitiesApi.update(props.activity.id, payload)
      ElMessage.success('活动已更新')
    } else {
      await activitiesApi.create(payload)
      ElMessage.success('活动已记录')
    }
    emit('saved')
    emit('update:visible', false)
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

/** 取消：不发任何请求（未保存的改动自然丢弃）。 */
function close(): void {
  emit('update:visible', false)
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
      <el-form-item label="标题" required>
        <el-input v-model="form.title" placeholder="如：家庭团圆饭" />
      </el-form-item>
      <el-form-item label="时间">
        <el-date-picker
          v-model="form.occurred_at"
          type="datetime"
          value-format="x"
          clearable
          class="full"
        />
      </el-form-item>
      <el-form-item label="地点">
        <el-input v-model="form.location" placeholder="选填" />
      </el-form-item>
      <el-form-item label="参与的人">
        <el-select
          v-model="form.participant_ids"
          multiple
          filterable
          placeholder="从名册选择（可多选）"
        >
          <el-option v-for="opt in options" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="图片">
        <ImageUploader v-model="form.images" />
      </el-form-item>
      <el-form-item label="详情">
        <el-input
          v-model="form.detail"
          type="textarea"
          :rows="3"
          placeholder="发生了什么、聊了什么（选填）"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button text @click="close">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="!canSubmit" @click="submit">
        保存
      </el-button>
    </template>
  </el-dialog>
</template>
