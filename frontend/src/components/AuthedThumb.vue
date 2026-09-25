<script setup lang="ts">
/** 鉴权缩略图：拿 blob URL 渲染，取不到时显示占位块。 */
import { useAuthedImage } from '@/composables/useAuthedImage'

const props = defineProps<{ path: string | null; variant?: 'thumb' | 'full' }>()
const { blobUrl, failed } = useAuthedImage(() => props.path)
</script>

<template>
  <img v-if="blobUrl" :src="blobUrl" class="image" :class="variant ?? 'thumb'" alt="" />
  <div v-else class="placeholder" :class="[variant ?? 'thumb', { failed }]" />
</template>

<style scoped>
.image,
.placeholder {
  object-fit: cover;
  border-radius: var(--crm-radius-control);
  border: 1px solid var(--crm-line);
}
.thumb {
  width: 96px;
  height: 96px;
}
/* 大图变体：查看器里按容器宽度铺满，保持比例不裁切 */
.full {
  width: 100%;
  max-height: 60vh;
  object-fit: contain;
  border: none;
}
.placeholder {
  background: var(--crm-bone);
}
</style>
