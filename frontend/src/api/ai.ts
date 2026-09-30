/** ai 模块 API 封装：对话（SSE）、工具清单、写入提议确认，对应 backend ai/api.py */
import { api } from './client'
import type {
  AiEmbeddingConfigIn,
  AiEmbeddingConfigOut,
  AiLlmConfigIn,
  AiLlmConfigOut,
  AiSessionOut,
  AiTestOut,
  HistoryMessageOut,
  PendingActionOut,
  RebuildOut,
  SearchItemOut,
  ToolOut,
} from './types'

export interface ChatStreamEvent {
  type: 'start' | 'text' | 'tool' | 'error' | 'done'
  session_id?: string
  delta?: string
  name?: string
  code?: string
  message?: string
}

export const aiApi = {
  /** 工具清单（与 /mcp 对外暴露的能力同源）。 */
  tools: () => api.get<ToolOut[]>('/ai/tools'),
  /** 我的待确认写入提议。 */
  pendingList: () => api.get<PendingActionOut[]>('/ai/pending'),
  /** 确认提议（以提议人身份执行）。 */
  approve: (id: number) => api.post<PendingActionOut>(`/ai/pending/${id}/approve`),
  /** 拒绝提议。 */
  reject: (id: number) => api.post<PendingActionOut>(`/ai/pending/${id}/reject`),
  /** 我的会话列表（按最后活跃倒序）。 */
  sessions: () => api.get<AiSessionOut[]>('/ai/sessions'),
  /** 某会话的历史消息（切换会话时用）。 */
  sessionMessages: (sessionId: string) =>
    api.get<HistoryMessageOut[]>(`/ai/sessions/${sessionId}/messages`),
  /** 删除会话（索引与对话内容一并清）。 */
  removeSession: (sessionId: string) => api.delete<void>(`/ai/sessions/${sessionId}`),

  /**
   * 对话流：POST + SSE。onEvent 逐帧回调；返回 Promise 在流结束时 resolve。
   * 手工 fetch（EventSource 不支持 POST/鉴权头）。
   */
  chat: async (
    message: string,
    sessionId: string | null,
    onEvent: (event: ChatStreamEvent) => void,
    images: string[] = [],
  ) => {
    const auth = await import('@/stores/auth')
    const store = auth.useAuthStore()
    const response = await fetch('/api/v1/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${store.token}` },
      // images 为空时不带该字段（undefined 不序列化），后端契约向后兼容
      body: JSON.stringify({
        message,
        session_id: sessionId,
        images: images.length ? images : undefined,
      }),
    })
    if (!response.ok || !response.body) {
      throw new Error(`对话请求失败（${response.status}）`)
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let separator = buffer.indexOf('\n\n')
      while (separator !== -1) {
        const frame = buffer.slice(0, separator)
        buffer = buffer.slice(separator + 2)
        if (frame.startsWith('data: ')) {
          onEvent(JSON.parse(frame.slice(6)) as ChatStreamEvent)
        }
        separator = buffer.indexOf('\n\n')
      }
    }
  },
}

export const embeddingsApi = {
  /** 重建语义索引（全量对账：新增/变更重算、消失清理）。 */
  rebuild: () => api.post<RebuildOut>('/ai/embeddings/rebuild'),
}

export const searchApi = {
  /** 语义搜索：按含义跨类型检索（联系人/活动/礼物/资金/备注），权限在后端已过滤。 */
  search: (q: string) =>
    api.get<SearchItemOut[]>(`/ai/search?${new URLSearchParams({ q }).toString()}`),
}

export const settingsApi = {
  /** 读取 LLM 配置（未配置 configured=false）。 */
  aiConfig: () => api.get<AiLlmConfigOut>('/settings/ai'),
  /** 保存 LLM 配置。 */
  saveAiConfig: (data: AiLlmConfigIn) => api.put<AiLlmConfigOut>('/settings/ai', data),
  /** 连接测试（真实发一次最小补全）。 */
  testAi: (data: AiLlmConfigIn) => api.post<AiTestOut>('/settings/ai/test', data),
  /** 读取 Embedding 配置。 */
  embeddingConfig: () => api.get<AiEmbeddingConfigOut>('/settings/embedding'),
  /** 保存 Embedding 配置。 */
  saveEmbeddingConfig: (data: AiEmbeddingConfigIn) =>
    api.put<AiEmbeddingConfigOut>('/settings/embedding', data),
  /** 测试 Embedding 连接。 */
  testEmbedding: (data: AiEmbeddingConfigIn) => api.post<AiTestOut>('/settings/embedding/test', data),
  /** 读取高德 key 配置（未配置 configured=false；已配置回显掩码）。 */
  amapConfig: () =>
    api.get<{ configured: false } | { configured: true; api_key_masked: string }>(
      '/settings/geo/amap',
    ),
  /** 保存高德 key（Web 服务类型）。 */
  saveAmapConfig: (data: { api_key: string }) =>
    api.put<{ configured: boolean }>('/settings/geo/amap', data),
  /** 测试高德 key（真实解析一次固定地址）。 */
  testAmap: (data: { api_key: string }) => api.post<AiTestOut>('/settings/geo/amap/test', data),
}
