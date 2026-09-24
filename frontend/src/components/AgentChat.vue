<script setup lang="ts">
/** Agent 对话组件：SSE 流式渲染 + 工具调用状态 + 写入提议确认。
 * 对话页与悬浮球浮层共用（compact 属性控制密度）。 */
import { nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { aiApi, type ChatStreamEvent } from '@/api/ai'
import { ApiError } from '@/api/client'
import { tokens } from '@/design/tokens'
import type { PendingActionOut } from '@/api/types'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  /** 该条消息过程中的工具调用名（展示为状态行）。 */
  tools: string[]
  /** 该条消息产生的待确认提议编号（点击可跳转确认）。 */
  pendingHint?: string
}

const props = defineProps<{ compact?: boolean }>()

const messages = ref<ChatMessage[]>([])
const input = ref('')
const streaming = ref(false)
const threadId = ref<string | null>(null)
const pendingActions = ref<PendingActionOut[]>([])
const showPending = ref(false)
const listHost = ref<HTMLDivElement | null>(null)

/** 追加一条 assistant 消息并保持滚动到底部。 */
function appendAssistant(): ChatMessage {
  const item: ChatMessage = { role: 'assistant', content: '', tools: [] }
  messages.value.push(item)
  return item
}

async function scrollToBottom(): Promise<void> {
  await nextTick()
  listHost.value?.scrollTo({ top: listHost.value.scrollHeight })
}

/** 发送消息：消费 SSE 帧，增量渲染文本/工具状态。 */
async function send(): Promise<void> {
  const text = input.value.trim()
  if (!text || streaming.value) return
  input.value = ''
  messages.value.push({ role: 'user', content: text, tools: [] })
  const reply = appendAssistant()
  streaming.value = true
  try {
    await aiApi.chat(text, threadId.value, (event: ChatStreamEvent) => {
      handleEvent(event, reply)
    })
  } catch (error) {
    reply.content += error instanceof Error ? error.message : '对话请求失败'
  } finally {
    streaming.value = false
    await scrollToBottom()
    await refreshPending()
  }
}

function handleEvent(event: ChatStreamEvent, reply: ChatMessage): void {
  if (event.type === 'start') {
    threadId.value = event.thread_id ?? threadId.value
    return
  }
  if (event.type === 'text' && event.delta) {
    reply.content += event.delta
    void scrollToBottom()
    return
  }
  if (event.type === 'tool' && event.name) {
    reply.tools.push(event.name)
    void scrollToBottom()
    return
  }
  if (event.type === 'error') {
    const hint = event.code === 'llm_not_configured' ? `${event.message}（右上角 ⚙ 进入设置）` : event.message
    reply.content += `⚠ ${hint ?? '处理失败'}`
  }
}

// ---- 待确认提议 ----
async function refreshPending(): Promise<void> {
  try {
    pendingActions.value = await aiApi.pendingList()
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) pendingActions.value = []
  }
}

/** 确认提议：执行结果以消息形式回灌对话流。 */
async function decide(action: PendingActionOut, approve: boolean): Promise<void> {
  try {
    const result = approve ? await aiApi.approve(action.id) : await aiApi.reject(action.id)
    const outcome = approve
      ? result.result?.ok
        ? `✅ ${result.result.message}`
        : `⚠ 执行失败：${result.result?.error ?? '未知原因'}`
      : '已拒绝该提议'
    messages.value.push({ role: 'assistant', content: outcome, tools: [] })
    await refreshPending()
    await scrollToBottom()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '操作失败')
  }
}

function payloadText(action: PendingActionOut): string {
  const parts = Object.entries(action.payload).map(([key, value]) => {
    const shown = Array.isArray(value) ? value.join('、') : String(value ?? '')
    return `${key}: ${shown}`
  })
  return parts.join(' · ')
}

onMounted(refreshPending)
</script>

<template>
  <div class="agent-chat" :class="{ compact: props.compact }">
    <div ref="listHost" class="msg-list">
      <div v-if="!messages.length" class="chat-empty">
        <p>我是你的家庭助理，可以查名册、看待办、查往来。</p>
        <p class="chat-empty-sub">试试：「我今天有什么事？」或「帮我记一下，明天给老爸打电话」</p>
      </div>
      <div v-for="(item, index) in messages" :key="index" class="msg" :class="item.role">
        <div v-for="tool in item.tools" :key="tool" class="msg-tool">
          <el-tag size="small">{{ tool }}</el-tag>
        </div>
        <div class="msg-bubble">{{ item.content }}<span v-if="streaming && index === messages.length - 1 && item.role === 'assistant'" class="cursor">▍</span></div>
      </div>
    </div>

    <div v-if="showPending" class="pending-panel">
      <div class="pending-head">
        <span>待确认的写入提议</span>
        <el-button text @click="showPending = false">收起</el-button>
      </div>
      <div v-for="action in pendingActions" :key="action.id" class="pending-item">
        <div class="pending-title">
          <el-tag size="small" type="warning">{{ action.tool_name }}</el-tag>
          <span>{{ payloadText(action) }}</span>
        </div>
        <div class="pending-actions">
          <el-button type="primary" @click="decide(action, true)">确认执行</el-button>
          <el-button text @click="decide(action, false)">拒绝</el-button>
        </div>
      </div>
      <p v-if="!pendingActions.length" class="pending-empty">没有待确认的提议</p>
    </div>

    <div class="composer">
      <el-button
        text
        :color="pendingActions.length ? tokens.color.seal : undefined"
        @click="showPending = !showPending"
      >
        待确认{{ pendingActions.length ? ` ${pendingActions.length}` : '' }}
      </el-button>
      <el-input
        v-model="input"
        :placeholder="streaming ? '助手思考中…' : '问我任何事，或让我帮你记一笔'"
        :disabled="streaming"
        @keydown.enter.prevent="send"
      />
      <el-button type="primary" :loading="streaming" :disabled="!input.trim()" @click="send">
        发送
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.agent-chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.msg-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chat-empty {
  margin: auto;
  text-align: center;
  color: var(--crm-muted);
  font-size: 14px;
  padding: 0 24px;
}
.chat-empty-sub {
  font-size: 13px;
  margin-top: 6px;
}
.msg {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.msg.user {
  align-items: flex-end;
}
.msg-bubble {
  max-width: 82%;
  padding: 9px 14px;
  border-radius: var(--crm-radius-float);
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg.user .msg-bubble {
  background: var(--crm-ink);
  color: #fff;
}
.msg.assistant .msg-bubble {
  background: var(--crm-bone);
  border: 1px solid var(--crm-line);
}
.cursor {
  animation: blink 1s steps(2) infinite;
}
@keyframes blink {
  to {
    opacity: 0;
  }
}
.msg-tool {
  opacity: 0.75;
}
.pending-panel {
  border-top: 1px solid var(--crm-line);
  background: var(--crm-bone);
  padding: 10px 14px;
  max-height: 200px;
  overflow-y: auto;
}
.pending-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: var(--crm-muted);
  margin-bottom: 8px;
}
.pending-item {
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-control);
  padding: 8px 10px;
  margin-bottom: 6px;
}
.pending-title {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
}
.pending-actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}
.pending-empty {
  color: var(--crm-muted);
  font-size: 13px;
  text-align: center;
}
.composer {
  display: flex;
  gap: 8px;
  padding: 12px 14px;
  border-top: 1px solid var(--crm-line);
  align-items: center;
}
.compact .msg-list {
  padding: 12px;
}
</style>
