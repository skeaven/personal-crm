<script setup lang="ts">
/**
 * 活动图片上传器：选图后逐张传到临时区，提交时由表单把临时路径一起提交；
 * 已有图片只带 id，保持「提交数组顺序即展示顺序」的全量替换语义。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, ApiError } from '@/api/client'
import { activityImageUrl } from '@/api/records'
import AuthedThumb from '@/components/AuthedThumb.vue'
import type { ImageRefIn } from '@/api/types'

const props = defineProps<{ modelValue: ImageRefIn[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: ImageRefIn[]] }>()

const ACCEPT = '.jpg,.jpeg,.png,.webp'
const MAX_IMAGES = 20
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const images = computed(() => props.modelValue)

/** 预览地址：已有图走鉴权端点，新上传的走临时区端点。 */
function previewPath(item: ImageRefIn): string | null {
  if (item.id !== undefined) return activityImageUrl(item.id, 'thumb')
  if (item.temp_path) return `/uploads/${item.temp_path}`
  return null
}

/** 打开系统文件选择框。 */
function pickFiles(): void {
  fileInput.value?.click()
}

/** 逐张串行上传（家庭网络下并发上传会互相挤占带宽，且便于逐个报错）。 */
async function onFilesSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = '' // 允许重复选同一个文件
  if (!files.length) return

  const room = MAX_IMAGES - images.value.length
  if (room <= 0) {
    ElMessage.warning(`最多 ${MAX_IMAGES} 张图片`)
    return
  }

  uploading.value = true
  const added: ImageRefIn[] = []
  try {
    for (const file of files.slice(0, room)) {
      const { temp_path: tempPath } = await api.uploadTemp(file)
      added.push({ temp_path: tempPath })
    }
    emit('update:modelValue', [...images.value, ...added])
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '图片上传失败')
  } finally {
    uploading.value = false
  }
}

/** 移除一张图：已有图不放进提交数组即等于删除（符合全量替换语义）。 */
function removeAt(index: number): void {
  const next = [...images.value]
  next.splice(index, 1)
  emit('update:modelValue', next)
}

/** 与相邻项交换位置，用于调整封面（首张即时间线封面）。 */
function move(index: number, delta: number): void {
  const target = index + delta
  if (target < 0 || target >= images.value.length) return
  const next = [...images.value]
  ;[next[index], next[target]] = [next[target], next[index]]
  emit('update:modelValue', next)
}
</script>

<template>
  <div class="uploader">
    <div class="grid">
      <div v-for="(item, index) in images" :key="item.id ?? item.temp_path" class="cell">
        <AuthedThumb :path="previewPath(item)" />
        <span v-if="index === 0" class="cover">封面</span>
        <div class="actions">
          <el-button text size="small" :disabled="index === 0" @click="move(index, -1)">
            前移
          </el-button>
          <el-button
            text
            size="small"
            :disabled="index === images.length - 1"
            @click="move(index, 1)"
          >
            后移
          </el-button>
          <el-button text size="small" type="danger" @click="removeAt(index)">删除</el-button>
        </div>
      </div>

      <button v-if="images.length < MAX_IMAGES" class="add" type="button" @click="pickFiles">
        <span>{{ uploading ? '上传中…' : '+ 添加图片' }}</span>
      </button>
    </div>

    <p class="hint">第一张作为封面显示在联系人往来里；支持 jpg / png / webp，单张不超过 10MB</p>
    <input ref="fileInput" type="file" :accept="ACCEPT" multiple hidden @change="onFilesSelected" />
  </div>
</template>

<style scoped>
.grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.cell {
  position: relative;
  width: 96px;
}
.cover {
  position: absolute;
  top: 4px;
  left: 4px;
  padding: 1px 6px;
  border-radius: var(--crm-radius-control);
  background: var(--crm-seal);
  color: #fff;
  font-size: 12px;
}
.actions {
  display: flex;
  justify-content: center;
  gap: 2px;
}
.add {
  width: 96px;
  height: 96px;
  border: 1px dashed var(--crm-line);
  border-radius: var(--crm-radius-control);
  background: var(--crm-bone);
  color: var(--crm-muted);
  cursor: pointer;
  font-size: 13px;
}
.hint {
  margin: 8px 0 0;
  color: var(--crm-muted);
  font-size: 12px;
}
</style>
