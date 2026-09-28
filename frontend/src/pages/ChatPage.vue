<script setup lang="ts">
/** 助理页：左侧会话列表 + 右侧对话区。
 *
 * session_id 由前端生成（crypto.randomUUID）——后端按它持久化，见 D20。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { aiApi } from '@/api/ai'
import { ApiError } from '@/api/client'
import AgentChat from '@/components/AgentChat.vue'
import SessionList from '@/components/SessionList.vue'
import type { AiSessionOut } from '@/api/types'

const sessions = ref<AiSessionOut[]>([])
const activeSessionId = ref<string>('')

/** 刷新会话列表（按最后活跃倒序，后端已排序）。 */
async function loadSessions(): Promise<void> {
  try {
    sessions.value = await aiApi.sessions()
    // 空列表（首次使用）或当前会话已被删：开一个新对话
    if (!sessions.value.some((item) => item.session_id === activeSessionId.value)) {
      activeSessionId.value = sessions.value[0]?.session_id ?? newSessionId()
    }
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('会话列表加载失败')
  }
}

/** 生成新会话标识（前端是权威来源，后端不生成）。 */
function newSessionId(): string {
  return crypto.randomUUID()
}

/** 开一个新对话（此时还没有索引行，首轮提问后才会出现在列表里）。 */
function createSession(): void {
  activeSessionId.value = newSessionId()
}

/** 删除会话并切到下一个（没有剩余则开新对话）。 */
async function removeSession(sessionId: string): Promise<void> {
  try {
    await aiApi.removeSession(sessionId)
    ElMessage.success('对话已删除')
    if (sessionId === activeSessionId.value) activeSessionId.value = ''
    await loadSessions()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '删除失败')
  }
}

onMounted(loadSessions)
</script>

<template>
  <div class="crm-page assistant-page">
    <header class="page-head">
      <div>
        <h1 class="page-title crm-display">助 手</h1>
        <p class="page-sub">自然语言查名册、记待办、记活动；写入需你确认后生效</p>
      </div>
      <a class="crm-link" href="/settings">LLM 设置</a>
    </header>
    <div class="chat-layout">
      <SessionList
        :sessions="sessions"
        :active-id="activeSessionId"
        @select="activeSessionId = $event"
        @create="createSession"
        @remove="removeSession"
      />
      <div class="chat-card">
        <AgentChat :session-id="activeSessionId" @updated="loadSessions" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.assistant-page {
  height: calc(100vh - 88px);
  display: flex;
  flex-direction: column;
}
.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-title {
  margin: 0;
  font-size: 32px;
}
.page-sub {
  margin: 8px 0 0;
  color: var(--crm-muted);
  font-size: 14px;
}
/* 两栏：会话列表定宽、对话区自适应 */
.chat-layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 16px;
}
.chat-card {
  min-height: 0;
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
  overflow: hidden;
}
/* 窄屏退化为上下排列（列表在上） */
@media (max-width: 720px) {
  .chat-layout {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
  }
}
</style>