<script setup lang="ts">
/**
 * 活动图片查看器：拉该活动的全部图片（按展示顺序），支持左右翻看。
 * 图片走鉴权端点，所以用 AuthedThumb 的 full 变体而不是原生 img。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { activitiesApi, activityImageUrl } from '@/api/records'
import { ApiError } from '@/api/client'
import AuthedThumb from '@/components/AuthedThumb.vue'

const props = defineProps<{ visible: boolean; activityId: number | null }>()
const emit = defineEmits<{ 'update:visible': [value: boolean] }>()

const imageIds = ref<number[]>([])
const index = ref(0)

const currentPath = computed(() =>
  imageIds.value.length ? activityImageUrl(imageIds.value[index.value]) : null,
)
const total = computed(() => imageIds.value.length)

watch(
  () => props.visible,
  async (opened) => {
    if (!opened || props.activityId === null) return
    index.value = 0
    imageIds.value = []
    try {
      // 归一记录只带封面 id，所以点开时按 id 拉一次详情取全部图片
      const activity = await activitiesApi.get(props.activityId)
      imageIds.value = [...activity.images]
        .sort((left, right) => left.sort_order - right.sort_order)
        .map((image) => image.id)
    } catch (error) {
      ElMessage.error(error instanceof ApiError ? error.message : '图片加载失败')
    }
  },
  { immediate: true },
)
</script>

<template>
  <el-dialog
    :model-value="visible"
    title="活动图片"
    width="720px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <div v-if="total" class="viewer">
      <AuthedThumb :path="currentPath" variant="full" />
      <div class="nav">
        <el-button :disabled="index === 0" @click="index -= 1">上一张</el-button>
        <span class="counter">{{ index + 1 }} / {{ total }}</span>
        <el-button :disabled="index === total - 1" @click="index += 1">下一张</el-button>
      </div>
    </div>
    <p v-else class="empty">这个活动还没有图片</p>
  </el-dialog>
</template>

<style scoped>
.viewer {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
}
.counter {
  color: var(--crm-muted);
  font-size: 13px;
}
.empty {
  margin: 0;
  color: var(--crm-muted);
  text-align: center;
}
</style>
