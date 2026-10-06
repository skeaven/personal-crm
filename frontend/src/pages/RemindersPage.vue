<script setup lang="ts">
/** 提醒页：主动提醒的查看与已读（D22）。
 * 来源徽标 + 跳转（日期→联系人详情、任务→待办、还款→资金）；
 * 手动扫描兜底（正常由后端每小时的调度器生成）。 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { remindersApi } from '@/api/reminders'
import { ApiError } from '@/api/client'
import { useUnreadReminders } from '@/composables/useUnreadReminders'
import type { ReminderOut } from '@/api/types'

const router = useRouter()
// 标记已读/扫描后同步导航徽标，避免它挂着旧数字直到下一轮 60s 轮询
const { refreshUnreadCount } = useUnreadReminders()

const loading = ref(false)
const unreadOnly = ref(false)
const reminders = ref<ReminderOut[]>([])
const scanning = ref(false)

/** 未读数（供"全部已读"按钮的可用性与页头摘要）。 */
const unreadTotal = computed(() => reminders.value.filter((r) => !r.read_at).length)

const sourceLabels: Record<string, string> = {
  date: '日期',
  task: '任务',
  repayment: '还款',
}

/** 来源跳转：日期/任务/还款各回各的管理页（日期带联系人直达详情）。 */
function goTarget(item: ReminderOut): void {
  if (item.source === 'date' && item.contact_id) {
    void router.push(`/contacts/${item.contact_id}`)
    return
  }
  const to: Record<string, string> = { task: '/tasks', repayment: '/funds' }
  if (to[item.source]) void router.push(to[item.source])
}

/** 剩余时间文案（快照 days_left：正=临近，负=已过期）。 */
function whenLabel(item: ReminderOut): string {
  if (item.days_left === 0) return '就是今天'
  if (item.days_left > 0) return `还有 ${item.days_left} 天`
  return `过期 ${-item.days_left} 天`
}

async function load(): Promise<void> {
  loading.value = true
  try {
    reminders.value = await remindersApi.list(unreadOnly.value)
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('提醒加载失败')
  } finally {
    loading.value = false
  }
}

async function markRead(item: ReminderOut): Promise<void> {
  try {
    await remindersApi.markRead(item.id)
    item.read_at = new Date().toISOString()
    void refreshUnreadCount()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '操作失败')
  }
}

async function markAll(): Promise<void> {
  try {
    await remindersApi.markAllRead()
    ElMessage.success('全部已读')
    await load()
    void refreshUnreadCount()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '操作失败')
  }
}

/** 手动扫描：正常由后端每小时调度；此处供"刚记完一笔想立即看到提醒"。 */
async function scan(): Promise<void> {
  scanning.value = true
  try {
    const stats = await remindersApi.scan()
    ElMessage.success(`扫描完成：新增 ${stats.created} 条`)
    await load()
    void refreshUnreadCount()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '扫描失败')
  } finally {
    scanning.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="crm-page">
    <header class="crm-page-head">
      <div>
        <h1 class="crm-page-title crm-display">提 醒</h1>
        <p class="crm-page-sub">
          {{ unreadTotal > 0 ? `${unreadTotal} 条未读` : '没有未读提醒' }}
          · 到期前 7 天内自动生成（生日/纪念日、任务、还款）
        </p>
      </div>
      <div class="actions">
        <el-button text :loading="scanning" @click="scan">立即扫描</el-button>
        <el-button :disabled="unreadTotal === 0" @click="markAll">全部已读</el-button>
      </div>
    </header>

    <div class="toolbar">
      <el-radio-group v-model="unreadOnly" @change="load">
        <el-radio-button :value="false">全部</el-radio-button>
        <el-radio-button :value="true">未读</el-radio-button>
      </el-radio-group>
    </div>

    <el-table
      v-if="reminders.length"
      :data="reminders"
      class="reminder-table"
      :row-class-name="(ctx: { row: ReminderOut }) => (ctx.row.read_at ? '' : 'unread-row')"
    >
      <el-table-column label="提醒" min-width="320">
        <template #default="{ row }">
          <div class="title-cell" @click="goTarget(row)">
            <el-tag size="small">{{ sourceLabels[row.source] ?? row.source }}</el-tag>
            <span class="title-text" :class="{ read: row.read_at }">{{ row.title }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="到期" width="130">
        <template #default="{ row }">{{ row.due_date }}</template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <span class="when" :class="{ urgent: row.days_left <= 0 }">{{ whenLabel(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" align="right" fixed="right">
        <template #default="{ row }">
          <el-button text size="small" @click="goTarget(row)">查看</el-button>
          <el-button v-if="!row.read_at" text size="small" @click="markRead(row)">已读</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-else-if="!loading" description="没有提醒——临近的生日、到期任务和还款会出现在这里" />
  </div>
</template>

<style scoped>
.actions {
  display: flex;
  gap: 8px;
}
.toolbar {
  margin-bottom: 12px;
}
.reminder-table {
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
  min-width: 0;
}
.title-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}
.title-text {
  font-size: 15px;
}
.title-text.read {
  color: var(--crm-muted);
}
.when {
  color: var(--crm-muted);
  font-size: 13px;
}
.when.urgent {
  color: var(--crm-seal);
}
:deep(.unread-row) {
  font-weight: 600;
}
</style>
