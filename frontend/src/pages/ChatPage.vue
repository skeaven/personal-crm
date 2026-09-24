<script setup lang="ts">
/** 助手页：全屏的 agent 对话（与悬浮球浮层共用 AgentChat 组件）。 */
import AgentChat from '@/components/AgentChat.vue'
</script>

<template>
  <div class="assistant-page">
    <header class="page-head">
      <div>
        <h1 class="page-title crm-display">助 手</h1>
        <p class="page-sub">自然语言查名册、记待办、记活动；写入需你确认后生效</p>
      </div>
      <a class="crm-link" href="/settings">LLM 设置</a>
    </header>
    <div class="chat-card">
      <AgentChat />
    </div>
  </div>
</template>

<style scoped>
.assistant-page {
  max-width: var(--crm-content-max-width, 1080px);
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
.chat-card {
  flex: 1;
  min-height: 0;
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
  overflow: hidden;
}
</style>
