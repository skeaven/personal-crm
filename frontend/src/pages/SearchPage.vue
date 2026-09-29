<script setup lang="ts">
/** 搜索页：语义检索入口（D6.3）——跨联系人/活动/礼物/资金/备注按含义找，不是关键字匹配。 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { searchApi } from '@/api/ai'
import { ApiError } from '@/api/client'
import SearchResults from '@/components/SearchResults.vue'
import type { SearchItemOut } from '@/api/types'

const router = useRouter()

const keyword = ref('')
const loading = ref(false)
const searched = ref(false)
const results = ref<SearchItemOut[]>([])
const errorMessage = ref('')
/** 配置类错误（未配 Embedding）才给「去设置页」入口，网络/上游故障不该往设置页引。 */
const configIssue = ref(false)

/**
 * 执行搜索。语义搜索每查一次都要调一次 embedding 接口，因此只在回车/点击时触发，
 * 做成输入即搜会白烧调用；另外空词不请求。
 */
async function runSearch(): Promise<void> {
  const query = keyword.value.trim()
  if (!query || loading.value) {
    return
  }
  loading.value = true
  errorMessage.value = ''
  configIssue.value = false
  try {
    results.value = await searchApi.search(query)
  } catch (error) {
    results.value = []
    errorMessage.value = error instanceof ApiError ? error.message : '搜索失败，请稍后重试'
    configIssue.value = error instanceof ApiError && error.status === 400
  } finally {
    searched.value = true
    loading.value = false
  }
}

/** 联系人结果可点进详情页；活动/礼物/资金/备注暂无详情页，只展示内容。 */
function openResult(item: SearchItemOut): void {
  if (item.entity_type === 'contact') {
    router.push(`/contacts/${item.entity_id}`)
  }
}
</script>

<template>
  <div class="crm-page">
    <header class="page-head">
      <div>
        <h1 class="page-title crm-display">搜 索</h1>
        <p class="page-sub">按含义找人、找事、找记录</p>
      </div>
    </header>

    <div class="toolbar">
      <!-- data-test 挂包裹层：el-input 会把额外属性透传到内层 input，挂在组件上选择器易落空 -->
      <div class="search" data-test="search-input">
        <el-input
          v-model="keyword"
          placeholder="例如：爱养花的长辈、送过白酒的人、搬家来帮忙的"
          clearable
          @keyup.enter="runSearch"
        />
      </div>
      <el-button type="primary" :loading="loading" @click="runSearch">搜索</el-button>
    </div>

    <div v-if="errorMessage" class="notice">
      <span class="notice-text">{{ errorMessage }}</span>
      <el-button
        v-if="configIssue"
        text
        type="primary"
        data-test="goto-settings"
        @click="router.push('/settings')"
      >
        去设置页
      </el-button>
    </div>

    <SearchResults v-if="results.length" :items="results" @open="openResult" />

    <p v-else-if="searched && !errorMessage" class="empty">
      没有找到相关内容。刚录入的数据需要先在设置页重建语义索引，才会被检索到。
    </p>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}
.search {
  max-width: 420px;
}
.notice {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--crm-radius-control);
  background: var(--crm-seal-soft);
  color: var(--crm-seal);
  font-size: 13px;
}
.notice-text {
  flex: 1;
}
.empty {
  margin: 24px 0;
  color: var(--crm-muted);
  font-size: 13px;
  text-align: center;
}
</style>
