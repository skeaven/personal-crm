<script setup lang="ts">
/** 主页：进入系统的默认页。
 * 布局 = 统计卡行（点击跳名册/待办并带过滤）+ 左待办区（临近事项）
 *       + 右关系图谱预留卡（静态占位，L2 3D 渲染选型后替换）。 */
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { dashboardApi } from '@/api/dashboard'
import { graphApi } from '@/api/graph'
import { ApiError } from '@/api/client'
import RelationGraphGL from '@/components/RelationGraphGL.vue'
import type { DashboardStatsOut, GraphDataOut, TodoItemOut } from '@/api/types'

const router = useRouter()

const loading = ref(false)
const stats = ref<DashboardStatsOut | null>(null)
const todos = ref<TodoItemOut[]>([])
const graphData = ref<GraphDataOut>({ nodes: [], links: [] })
const todoTableRef = ref()

/** 页头日期（中文习惯：9 月 21 日 星期一）。 */
const todayLabel = computed(() => {
  const now = new Date()
  const weekday = ['日', '一', '二', '三', '四', '五', '六'][now.getDay()]
  return `${now.getMonth() + 1} 月 ${now.getDate()} 日 星期${weekday}`
})

/** 统计卡定义：数字 + 标签 + 去向（名册过滤或待办页）。 */
const statCards = computed(() => {
  const value = stats.value
  if (!value) return []
  return [
    { label: '联系人', count: value.total_contacts, to: '/contacts' },
    {
      label: '近 30 天联系过',
      count: value.recent_contacted,
      to: '/contacts?activity=recent_30d',
    },
    {
      label: '超过半年未联系',
      count: value.stale_half_year,
      to: '/contacts?activity=stale_180d',
      warn: value.stale_half_year > 0,
    },
    { label: '进行中的待办', count: value.open_tasks, to: '/tasks' },
  ]
})

/** 主页只展示最临近的几条待办，完整视图在待办页。 */
const upcomingTodos = computed(() => todos.value.slice(0, 6))

const sourceLabel: Record<string, string> = {
  task: '任务',
  wish: '心愿',
  repayment: '还款',
  activity: '活动',
  birthday: '生日',
}

function daysLabel(item: TodoItemOut): string {
  if (item.days_left === null) return ''
  if (item.days_left === 0) return '就是今天'
  if (item.days_left > 0) return `还有 ${item.days_left} 天`
  return `过期 ${-item.days_left} 天`
}

/** el-table 行主键：来源 + 引用 id 组合，与原 v-for key 口径一致。 */
function todoRowKey(row: TodoItemOut): string {
  return `${row.source}-${row.ref_id}`
}

function openTodo(item: TodoItemOut): void {
  if (item.source === 'birthday' && item.contact_id) {
    router.push(`/contacts/${item.contact_id}`)
    return
  }
  const to: Record<string, string> = {
    task: '/tasks',
    wish: '/wishlist',
    repayment: '/funds',
    activity: '/activities',
  }
  if (to[item.source]) router.push(to[item.source])
}

async function loadHome(): Promise<void> {
  loading.value = true
  try {
    const [statsResult, todoResult, graphResult] = await Promise.all([
      dashboardApi.stats(),
      dashboardApi.todos('todo'),
      graphApi.graphData(),
    ])
    stats.value = statsResult
    todos.value = todoResult
    graphData.value = graphResult
    // el-table 在 grid 两列布局下挂载时列宽测算可能为空（表头表体错位），数据就位后强制重排
    await nextTick()
    todoTableRef.value?.doLayout()
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('主页加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadHome)
</script>

<template>
  <div class="crm-page home-page">
    <header class="page-head">
      <div>
        <h1 class="page-title crm-display">主 页</h1>
        <p class="page-sub">今天是 {{ todayLabel }}</p>
      </div>
    </header>

    <div class="stat-row">
      <el-card
        v-for="card in statCards"
        :key="card.label"
        shadow="hover"
        class="stat-card"
        @click="router.push(card.to)"
      >
        <span class="stat-count crm-display" :class="{ warn: card.warn }">{{ card.count }}</span>
        <span class="stat-label">{{ card.label }}</span>
      </el-card>
    </div>

    <div class="home-body">
      <section class="todo-panel">
        <div class="panel-head">
          <h2 class="panel-title">临近的事</h2>
          <el-button text @click="router.push('/tasks')">全部待办</el-button>
        </div>
        <!-- 来源 tag / 事项 / 剩余时间 三列；行点击跳转与原手写行一致 -->
        <el-table
          ref="todoTableRef"
          v-if="upcomingTodos.length"
          :data="upcomingTodos"
          :row-key="todoRowKey"
          class="todo-table"
          :row-style="{ cursor: 'pointer' }"
          @row-click="openTodo"
        >
          <el-table-column label="来源" width="96">
            <template #default="{ row }">
              <el-tag size="small">{{ sourceLabel[row.source] ?? row.source }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="事项" min-width="160">
            <template #default="{ row }">
              <span class="todo-title">{{ row.title }}</span>
            </template>
          </el-table-column>
          <el-table-column label="剩余时间" width="120" align="right">
            <template #default="{ row }">
              <span
                v-if="daysLabel(row)"
                class="todo-when"
                :class="{ urgent: row.days_left !== null && row.days_left <= 3 }"
              >
                {{ daysLabel(row) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else-if="!loading" description="没有临近的事，安心" class="empty" />
      </section>

      <section class="graph-panel">
        <div class="panel-head">
          <h2 class="panel-title">关系图谱</h2>
          <el-button text @click="router.push('/graph')">进入图谱</el-button>
        </div>
        <div v-loading="loading" class="graph-stage">
          <RelationGraphGL
            v-if="graphData.nodes.length"
            :data="graphData"
            @node-click="(id: number) => router.push(`/contacts/${id}`)"
          />
          <el-empty v-else-if="!loading" description="添加联系人后，这里会长出你的关系网络" class="graph-empty" />
          <div v-else class="graph-count">{{ graphData.nodes.length }} 位联系人 · {{ graphData.links.length }} 条关系</div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.home-page {
  max-width: none;
}
.page-head {
  margin-bottom: 24px;
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
.stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 28px;
}
/* 卡片外壳交给 el-card（hover 阴影/边框走官方组件），这里只管数字排版与可点击 */
.stat-card {
  cursor: pointer;
}
.stat-card :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 18px 20px;
}
.stat-count {
  font-size: 32px;
  line-height: 1;
}
.stat-count.warn {
  color: var(--crm-seal);
}
.stat-label {
  color: var(--crm-muted);
  font-size: 13px;
}
.home-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  align-items: stretch;
  /* grid 子项默认 min-width:auto，el-table 的最小内容宽会把列撑破视口 */
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}
.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 12px;
}
.panel-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.todo-table {
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
}
.todo-title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.todo-when {
  color: var(--crm-muted);
  font-size: 13px;
}
.todo-when.urgent {
  color: var(--crm-seal);
}
.todo-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.graph-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.graph-stage {
  flex: 1;
  min-height: 420px;
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
  position: relative;
  overflow: hidden;
  background: var(--crm-canvas);
}
.graph-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.graph-count {
  position: absolute;
  left: 14px;
  bottom: 10px;
  color: var(--crm-muted);
  font-size: 12px;
}
.empty {
  margin-top: 40px;
}
@media (max-width: 900px) {
  .stat-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .home-body {
    grid-template-columns: 1fr;
  }
}
</style>
