<script setup lang="ts">
/** 会话列表：新建 / 切换 / 删除。数据和动作都由父页面持有，本组件只负责展示与抛出意图。 */
import type { AiSessionOut } from '@/api/types'

defineProps<{ sessions: AiSessionOut[]; activeId: string | null }>()
const emit = defineEmits<{
  select: [sessionId: string]
  create: []
  remove: [sessionId: string]
}>()

/** 列表里的时间只到「日」：会话列表用于认出是哪次对话，精确到分没有意义。 */
function formatDay(value: string): string {
  return new Date(value).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}
</script>

<template>
  <aside class="session-list">
    <el-button class="new" type="primary" plain @click="emit('create')" data-test="new-session">
      新对话
    </el-button>
    <ul class="items">
      <li
        v-for="session in sessions"
        :key="session.session_id"
        class="item"
        :class="{ active: session.session_id === activeId }"
        data-test="session-item"
        @click="emit('select', session.session_id)"
      >
        <span class="title">{{ session.title }}</span>
        <span class="day">{{ formatDay(session.updated_at) }}</span>
        <el-popconfirm
          title="删除这个对话？"
          confirm-button-text="删除"
          cancel-button-text="取消"
          @confirm="emit('remove', session.session_id)"
        >
          <template #reference>
            <el-button text size="small" type="danger" @click.stop>删除</el-button>
          </template>
        </el-popconfirm>
      </li>
    </ul>
    <p v-if="!sessions.length" class="empty">还没有对话</p>
  </aside>
</template>

<style scoped>
.session-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.new {
  width: 100%;
}
.items {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
}
.item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 44px;
  padding: 6px 8px;
  border-radius: var(--crm-radius-control);
  border-bottom: 1px solid var(--crm-line);
  cursor: pointer;
  transition: background var(--crm-ease);
}
.item:hover {
  background: var(--crm-bone);
}
.item.active {
  background: var(--crm-bone);
}
.title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
}
.day {
  color: var(--crm-muted);
  font-size: 12px;
  flex-shrink: 0;
}
.empty {
  margin: 12px 0;
  color: var(--crm-muted);
  font-size: 13px;
  text-align: center;
}
</style>