<script setup lang="ts">
/**
 * 单类型往来时间线：按 source 拉对应模块的分页接口，滚动到底自动加载下一页。
 *
 * 拆成三个 Tab 各自分页后，前端不再依赖 dashboard 的聚合接口——聚合服务仍保留
 * 供 AI 工具 get_contact_timeline 使用。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { activitiesApi, activityImageUrl } from '@/api/records'
import { giftsApi } from '@/api/gifts'
import { fundsApi } from '@/api/funds'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import AuthedThumb from '@/components/AuthedThumb.vue'
import ActivityGalleryDialog from '@/components/ActivityGalleryDialog.vue'
import type { TimelineRecord, TimelineSource } from '@/api/types'

const props = defineProps<{ source: TimelineSource; contactId: number }>()
const emit = defineEmits<{
  'open-detail': [payload: { source: TimelineSource; record: TimelineRecord }]
}>()

const PAGE_SIZE = 20

/** 资金类别 → 中文标题（与旧聚合接口的口径一致）。 */
const FUND_LABELS: Record<string, string> = {
  loan: '借款',
  repayment: '还款',
  gift_money: '礼金',
  other: '其他',
}

const auth = useAuthStore()
const records = ref<TimelineRecord[]>([])
const total = ref(0)
const loading = ref(false)
const sentinel = ref<HTMLElement | null>(null)
const galleryVisible = ref(false)
const galleryActivityId = ref<number | null>(null)
let observer: IntersectionObserver | null = null

const hasMore = computed(() => records.value.length < total.value)

/** 活动 → 归一记录（封面取 sort_order 最小的一张）。 */
function fromActivity(raw: Record<string, unknown>): TimelineRecord {
  const images = (raw.images ?? []) as { id: number; sort_order: number }[]
  const cover = [...images].sort((left, right) => left.sort_order - right.sort_order)[0]
  return {
    id: raw.id as number,
    occurredAt: (raw.occurred_at as string | null) ?? null,
    title: raw.title as string,
    summary: (raw.location as string | null) ?? null,
    amount: null,
    direction: null,
    extraLabel: null,
    ownerUserId: raw.owner_user_id as number,
    coverImageId: cover?.id ?? null,
  }
}

/** 礼物 → 归一记录。 */
function fromGift(raw: Record<string, unknown>): TimelineRecord {
  return {
    id: raw.id as number,
    occurredAt: (raw.given_at as string | null) ?? null,
    title: raw.title as string,
    summary: (raw.description as string | null) ?? null,
    amount: (raw.amount as string | null) ?? null,
    direction: (raw.direction as string | null) ?? null,
    extraLabel: (raw.occasion as string | null) ?? null,
    ownerUserId: raw.owner_user_id as number,
    coverImageId: null,
  }
}

/** 资金 → 归一记录（标题按类别生成）。 */
function fromFund(raw: Record<string, unknown>): TimelineRecord {
  return {
    id: raw.id as number,
    occurredAt: (raw.occurred_at as string | null) ?? null,
    title: FUND_LABELS[raw.category as string] ?? '资金事项',
    summary: (raw.description as string | null) ?? null,
    amount: (raw.amount as string | null) ?? null,
    direction: (raw.direction as string | null) ?? null,
    extraLabel: raw.status === 'settled' ? '已结清' : null,
    ownerUserId: raw.owner_user_id as number,
    coverImageId: null,
  }
}

/** 按 source 分派到对应模块的分页接口。 */
async function fetchPage(offset: number): Promise<{ items: TimelineRecord[]; total: number }> {
  const params = { contactId: props.contactId, limit: PAGE_SIZE, offset }
  if (props.source === 'activity') {
    const page = await activitiesApi.list(params)
    return { items: page.items.map((item) => fromActivity(item as never)), total: page.total }
  }
  if (props.source === 'gift') {
    const page = await giftsApi.list(params)
    return { items: page.items.map((item) => fromGift(item as never)), total: page.total }
  }
  const page = await fundsApi.list(params)
  return { items: page.items.map((item) => fromFund(item as never)), total: page.total }
}

/** 加载下一页并追加（首屏与滚动加载共用同一路径）。 */
async function loadMore(): Promise<void> {
  if (loading.value || !hasMore.value) return
  loading.value = true
  try {
    const page = await fetchPage(records.value.length)
    records.value = [...records.value, ...page.items]
    total.value = page.total
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('往来记录加载失败')
  } finally {
    loading.value = false
  }
}

/** 重置并重新加载首屏（保存/删除后由父页面调用）。 */
async function reload(): Promise<void> {
  records.value = []
  total.value = 0
  await loadMore()
}

/** 删除该条记录（按钮仅记录人本人可见，后端仍会独立校验）。 */
async function remove(record: TimelineRecord): Promise<void> {
  try {
    if (props.source === 'activity') await activitiesApi.remove(record.id)
    else if (props.source === 'gift') await giftsApi.remove(record.id)
    else await fundsApi.remove(record.id)
    ElMessage.success('已删除')
    await reload()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '删除失败')
  }
}

/** 打开该活动的图片查看器（只有活动源有图片）。 */
function openGallery(record: TimelineRecord): void {
  galleryActivityId.value = record.id
  galleryVisible.value = true
}

/** 时间戳展示：日期 + 时分；无日期给占位文案。 */
function formatTime(value: string | null): string {
  if (!value) return '未定时间'
  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** 金额展示：流出/送出为负号（与列表页口径一致）。 */
function amountText(record: TimelineRecord): string | null {
  if (!record.amount) return null
  const negative = record.direction === 'out' || record.direction === 'given'
  return `${negative ? '−' : '+'}¥${record.amount}`
}

onMounted(() => {
  observer = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) void loadMore()
  })
  if (sentinel.value) observer.observe(sentinel.value)
  void loadMore()
})

onBeforeUnmount(() => observer?.disconnect())

watch(() => props.contactId, reload)
watch(() => props.source, reload)

defineExpose({ reload })
</script>

<template>
  <el-timeline v-if="records.length">
    <el-timeline-item
      v-for="record in records"
      :key="`${source}-${record.id}`"
      :timestamp="formatTime(record.occurredAt)"
      placement="top"
    >
      <el-card shadow="always" class="tl-card crm-rise" :body-style="{ padding: '12px 16px' }">
        <div class="tl-head">
          <button
            v-if="record.coverImageId"
            type="button"
            class="cover-button"
            @click="openGallery(record)"
          >
            <AuthedThumb :path="activityImageUrl(record.coverImageId, 'thumb')" />
          </button>
          <div class="tl-main">
            <span class="tl-title">{{ record.title }}</span>
            <span v-if="amountText(record)" class="tl-amount">{{ amountText(record) }}</span>
          </div>
        </div>
        <div v-if="record.extraLabel || record.summary" class="tl-meta">
          <span v-if="record.extraLabel">{{ record.extraLabel }}</span>
          <span v-if="record.summary">{{ record.summary }}</span>
        </div>
        <div class="tl-actions">
          <el-button text size="small" @click="emit('open-detail', { source, record })">
            查看详情
          </el-button>
          <el-popconfirm
            v-if="record.ownerUserId === auth.user?.id"
            title="删除这条记录？"
            confirm-button-text="删除"
            cancel-button-text="取消"
            @confirm="remove(record)"
          >
            <template #reference>
              <el-button text size="small" type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </div>
      </el-card>
    </el-timeline-item>
  </el-timeline>
  <p v-else-if="!loading" class="empty">还没有往来记录</p>

  <div ref="sentinel" class="sentinel">
    <span v-if="loading" class="hint">加载中…</span>
    <span v-else-if="hasMore" class="hint">继续下滑，加载更早的记录…</span>
  </div>

  <ActivityGalleryDialog v-model:visible="galleryVisible" :activity-id="galleryActivityId" />
</template>

<style scoped>
.tl-card {
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
}
.tl-head {
  display: flex;
  gap: 12px;
  align-items: center;
}
.cover-button {
  padding: 0;
  border: none;
  background: none;
  cursor: pointer;
  flex-shrink: 0;
}
.tl-main {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.tl-title {
  font-size: 16px;
  color: var(--crm-ink);
}
.tl-amount {
  color: var(--crm-muted);
  font-size: 14px;
}
.tl-meta {
  display: flex;
  gap: 10px;
  margin-top: 6px;
  color: var(--crm-muted);
  font-size: 13px;
}
.tl-actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 6px;
}
.sentinel {
  padding: 8px 0 4px;
  text-align: center;
}
.hint,
.empty {
  color: var(--crm-muted);
  font-size: 13px;
}
.empty {
  margin: 0;
  padding: 12px 0;
}
</style>
