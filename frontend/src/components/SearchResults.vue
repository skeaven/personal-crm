<script setup lang="ts">
/** 语义搜索结果：按实体类型分组展示。取数与跳转由父页面负责，本组件只展示与抛意图。 */
import { computed } from 'vue'
import type { SearchItemOut } from '@/api/types'

const props = defineProps<{ items: SearchItemOut[] }>()
const emit = defineEmits<{ open: [item: SearchItemOut] }>()

/** 类型 → 中文标签；键的顺序即分组顺序。后端将来加新类型时走下面的兜底分支。 */
const TYPE_LABELS: Record<string, string> = {
  contact: '联系人',
  activity: '活动',
  gift: '礼物',
  fund: '资金',
  note: '备注',
}

interface ResultGroup {
  type: string
  label: string
  items: SearchItemOut[]
}

/** 未知类型的排名：排在全部已知类型之后，彼此保持后端返回顺序。 */
function rankOf(type: string): number {
  const index = Object.keys(TYPE_LABELS).indexOf(type)
  return index === -1 ? Object.keys(TYPE_LABELS).length : index
}

/** 按类型分组并排序；组内保持后端的距离升序。 */
const groups = computed<ResultGroup[]>(() => {
  const buckets = new Map<string, SearchItemOut[]>()
  for (const item of props.items) {
    const bucket = buckets.get(item.entity_type)
    if (bucket) {
      bucket.push(item)
    } else {
      buckets.set(item.entity_type, [item])
    }
  }
  return [...buckets.entries()]
    .map(([type, items]) => ({ type, label: TYPE_LABELS[type] ?? type, items }))
    .sort((a, b) => rankOf(a.type) - rankOf(b.type))
})
</script>

<template>
  <div class="search-results">
    <section
      v-for="group in groups"
      :key="group.type"
      class="group"
      data-test="search-group"
      :data-type="group.type"
    >
      <h2 class="group-label">{{ group.label }}</h2>
      <ul class="items">
        <li
          v-for="item in group.items"
          :key="`${item.entity_type}-${item.entity_id}`"
          class="item"
          :class="{ clickable: group.type === 'contact' }"
          data-test="search-item"
          :data-type="item.entity_type"
          @click="group.type === 'contact' && emit('open', item)"
        >
          <span class="content">{{ item.content }}</span>
          <span v-if="group.type === 'contact'" class="hint">查看</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.group + .group {
  margin-top: 20px;
}
.group-label {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--crm-muted);
}
.items {
  list-style: none;
  margin: 0;
  padding: 0;
}
.item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 10px 8px;
  border-bottom: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-control);
  font-size: 14px;
}
.item.clickable {
  cursor: pointer;
  transition: background var(--crm-ease);
}
.item.clickable:hover {
  background: var(--crm-bone);
}
.content {
  flex: 1;
  min-width: 0;
}
.hint {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--crm-muted);
}
</style>
