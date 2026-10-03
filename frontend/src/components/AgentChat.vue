<script setup lang="ts">
/** Agent 对话组件：SSE 流式渲染 + 工具调用状态 + 写入提议确认。
 * 由页面持有 sessionId（切换会话即载入历史），不自己管理会话标识。 */
import { nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api/client'
import { aiApi, type ChatStreamEvent } from '@/api/ai'
import { ApiError } from '@/api/client'
import { tokens } from '@/design/tokens'
import type { PendingActionOut } from '@/api/types'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  /** 该条消息过程中的工具调用名（展示为状态行）。 */
  tools: string[]
  /** 本轮带图时的本地预览地址（仅本次会话内存里；历史载入无图，见后端 ［图片］ 标记）。 */
  imagePreview?: string
  /** 该条消息产生的待确认提议编号（点击可跳转确认）。 */
  pendingHint?: string
}

const props = defineProps<{ sessionId: string }>()
const emit = defineEmits<{ updated: [] }>()

const messages = ref<ChatMessage[]>([])
const input = ref('')
const streaming = ref(false)
/** 正在进行中的工具调用名；收到文本增量即视为该工具已返回。 */
const activeTool = ref<string | null>(null)
const pendingActions = ref<PendingActionOut[]>([])
const showPending = ref(false)
const listHost = ref<HTMLDivElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const uploadingImage = ref(false)
/** 待发送图片：上传临时区后留路径 + 本地预览；只保留最后一张，发送后清空。 */
const pendingImage = ref<{ tempPath: string; previewUrl: string } | null>(null)

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

/** 载入该会话的历史消息（切换会话时调用；空会话得到空列表）。 */
async function loadHistory(): Promise<void> {
  messages.value = []
  activeTool.value = null
  if (!props.sessionId) return
  try {
    const history = await aiApi.sessionMessages(props.sessionId)
    messages.value = history.map((item) => ({
      role: item.role,
      content: item.content,
      tools: item.tools,
    }))
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('历史消息加载失败')
  }
}

watch(() => props.sessionId, loadHistory, { immediate: true })

/** 选中/拖入图片：先传临时区再预览。新图替换旧图，并回收旧预览的 object URL。 */
async function acceptImage(file: File): Promise<void> {
  uploadingImage.value = true
  const previous = pendingImage.value
  try {
    const { temp_path } = await api.uploadTemp(file)
    if (previous) URL.revokeObjectURL(previous.previewUrl)
    pendingImage.value = { tempPath: temp_path, previewUrl: URL.createObjectURL(file) }
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '图片上传失败')
  } finally {
    uploadingImage.value = false
  }
}

function clearImage(): void {
  if (pendingImage.value) URL.revokeObjectURL(pendingImage.value.previewUrl)
  pendingImage.value = null
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) void acceptImage(file)
  input.value = '' // 允许再次选择同一张图
}

function onDrop(event: DragEvent): void {
  const file = event.dataTransfer?.files?.[0]
  if (file) void acceptImage(file)
}

/** 发送消息：消费 SSE 帧，增量渲染文本/工具状态。带图可以没有文字（给默认指令）。 */
async function send(): Promise<void> {
  const text = input.value.trim()
  if ((!text && !pendingImage.value) || streaming.value) return
  input.value = ''
  const imageTemp = pendingImage.value?.tempPath
  const preview = pendingImage.value?.previewUrl
  clearImage()
  messages.value.push({ role: 'user', content: text, tools: [], imagePreview: preview })
  const reply = appendAssistant()
  streaming.value = true
  activeTool.value = null
  try {
    await aiApi.chat(
      text || '帮我看看这张图',
      props.sessionId,
      (event: ChatStreamEvent) => {
        handleEvent(event, reply)
      },
      imageTemp ? [imageTemp] : [],
    )
  } catch (error) {
    reply.content += error instanceof Error ? error.message : '对话请求失败'
  } finally {
    streaming.value = false
    activeTool.value = null
    await scrollToBottom()
    await refreshPending()
    emit('updated') // 首轮会产生会话索引行，让父页面刷新列表
  }
}

/** 事件分流：文本增量累积、工具调用进入进行中态。 */
function handleEvent(event: ChatStreamEvent, reply: ChatMessage): void {
  if (event.type === 'text' && event.delta) {
    reply.content += event.delta
    activeTool.value = null
    void scrollToBottom()
    return
  }
  if (event.type === 'tool' && event.name) {
    activeTool.value = event.name
    if (!reply.tools.includes(event.name)) reply.tools.push(event.name)
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

/** 工具名 → 中文（确认面板标题）；未映射的新工具回退原名。 */
const TOOL_LABELS: Record<string, string> = {
  create_task: '建待办',
  create_activity: '记活动',
  create_contact: '建联系人',
}
const CONTACT_FIELD_LABELS: Record<string, string> = {
  tier: '层级', name: '姓名', nickname: '昵称',
  organization: '单位', phone: '电话', qq: 'QQ', wechat: '微信',
  email: '邮箱', school_name: '院校', location: '所在地', bio: '备注',
}
const CONTACT_TIER_LABELS: Record<string, string> = { direct: '直接', edge: '边缘' }

/** create_contact 提议用中文标签渲染——确认的前提是看懂在确认什么。 */
function contactPayloadText(payload: Record<string, unknown>): string {
  return Object.entries(payload)
    .map(([key, value]) => {
      const shown = Array.isArray(value)
        ? value.join('、')
        : CONTACT_TIER_LABELS[String(value)] ?? String(value ?? '')
      return `${CONTACT_FIELD_LABELS[key] ?? key}: ${shown}`
    })
    .join(' · ')
}

function payloadText(action: PendingActionOut): string {
  if (action.tool_name === 'create_contact') return contactPayloadText(action.payload)
  const parts = Object.entries(action.payload).map(([key, value]) => {
    const shown = Array.isArray(value) ? value.join('、') : String(value ?? '')
    return `${key}: ${shown}`
  })
  return parts.join(' · ')
}

onMounted(refreshPending)
</script>

<template>
  <div class="agent-chat" @dragover.prevent @drop.prevent="onDrop">
    <div ref="listHost" class="msg-list">
      <div v-if="!messages.length" class="chat-empty">
        <p>我是你的家庭助理，可以查名册、看待办、查往来。</p>
        <p class="chat-empty-sub">试试：「我今天有什么事？」或「帮我记一下，明天给老爸打电话」</p>
      </div>
      <div v-for="(item, index) in messages" :key="index" class="msg" :class="item.role">
        <div v-for="tool in item.tools" :key="tool" class="msg-tool">
          <el-tag size="small">{{ tool }}</el-tag>
        </div>
        <img v-if="item.imagePreview" class="msg-image" :src="item.imagePreview" alt="附图" />
        <div class="msg-bubble">{{ item.content }}<span v-if="streaming && index === messages.length - 1 && item.role === 'assistant'" class="cursor">▍</span></div>
      </div>
    </div>

    <div v-if="activeTool" class="tool-running">
      <el-tag size="small" type="info">正在调用 {{ activeTool }}…</el-tag>
    </div>

    <div v-if="showPending" class="pending-panel">
      <div class="pending-head">
        <span>待确认的写入提议</span>
        <el-button text @click="showPending = false">收起</el-button>
      </div>
      <div v-for="action in pendingActions" :key="action.id" class="pending-item">
        <div class="pending-title">
          <el-tag size="small" type="warning">{{ TOOL_LABELS[action.tool_name] ?? action.tool_name }}</el-tag>
          <span>{{ payloadText(action) }}</span>
        </div>
        <div class="pending-actions">
          <el-button type="primary" @click="decide(action, true)">确认执行</el-button>
          <el-button text @click="decide(action, false)">拒绝</el-button>
        </div>
      </div>
      <p v-if="!pendingActions.length" class="pending-empty">没有待确认的提议</p>
    </div>

    <div v-if="pendingImage" class="image-preview" data-test="pending-image">
      <img :src="pendingImage.previewUrl" alt="待发送图片" />
      <el-button text size="small" @click="clearImage">移除</el-button>
    </div>

    <div class="composer">
      <input
        ref="fileInput"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        class="file-hidden"
        @change="onFileChange"
      />
      <el-button text :loading="uploadingImage" @click="fileInput?.click()">📎</el-button>
      <el-button
        text
        :color="pendingActions.length ? tokens.color.seal : undefined"
        @click="showPending = !showPending"
      >
        待确认{{ pendingActions.length ? ` ${pendingActions.length}` : '' }}
      </el-button>
      <!-- data-test 挂组件上会透传到内层 input，选择器直接可用（见 SearchPage 先例） -->
      <el-input
        v-model="input"
        data-test="chat-input"
        :placeholder="streaming ? '助手思考中…' : '问我任何事，或让我帮你记一笔'"
        :disabled="streaming"
        @keydown.enter.prevent="send"
      />
      <el-button
        type="primary"
        :loading="streaming"
        :disabled="!input.trim() && !pendingImage"
        data-test="send"
        @click="send"
      >
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
.file-hidden {
  display: none;
}
.image-preview {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px 8px;
}
.image-preview img {
  width: 72px;
  height: 72px;
  object-fit: cover;
  border-radius: var(--crm-radius-control);
  border: 1px solid var(--crm-line);
}
.msg-image {
  max-width: 180px;
  border-radius: var(--crm-radius-control);
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
.tool-running {
  padding: 4px 14px;
  border-top: 1px solid var(--crm-line);
}
</style>
