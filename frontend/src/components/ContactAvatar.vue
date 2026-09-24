<script setup lang="ts">
/** 联系人头像：展示名首字符的圆形中性头像（v3 极简：骨灰白底 + 墨色字符）。
 * 列表行与详情页共用；后续接入真实头像图（avatar_path）时在此组件内替换。 */
import { computed } from 'vue'

const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 36 })

const initial = computed(() => props.name.trim().charAt(0) || '？')
const fontSize = computed(() => `${Math.round(props.size * 0.42)}px`)
</script>

<template>
  <span
    class="contact-avatar"
    :style="{ width: `${size}px`, height: `${size}px`, fontSize }"
    aria-hidden="true"
  >{{ initial }}</span>
</template>

<style scoped>
.contact-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--crm-bone);
  border: 1px solid var(--crm-line);
  color: var(--crm-ink);
  font-weight: 500;
  line-height: 1;
  user-select: none;
}
</style>
