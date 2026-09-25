<script setup lang="ts">
/** 活动页：社交活动列表（搜索 + 页码分页）+ 共享表单弹窗（与详情页往来 Tab 同组件）。 */
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { activitiesApi } from '@/api/records'
import { ApiError } from '@/api/client'
import type { ActivityOut } from '@/api/types'
import { useContactOptions } from '@/composables/useContactOptions'
import ActivityFormDialog from '@/components/ActivityFormDialog.vue'

const { load: loadContacts, nameOf } = useContactOptions()

const PAGE_SIZE = 20
const loading = ref(false)
const search = ref('')
const activities = ref<ActivityOut[]>([])
const page = ref(1)
const total = ref(0)

const dialogVisible = ref(false)
const editingActivity = ref<ActivityOut | null>(null)

/** 拉取当前页（关键字搜索由后端执行；总数用于页码）。 */
async function loadActivities(): Promise<void> {
  loading.value = true
  try {
    const { items, total: count } = await activitiesApi.list({
      search: search.value || undefined,
      limit: PAGE_SIZE,
      offset: (page.value - 1) * PAGE_SIZE,
    })
    activities.value = items
    total.value = count
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('活动加载失败')
  } finally {
    loading.value = false
  }
}

/** 打开新建弹窗。 */
function openCreate(): void {
  editingActivity.value = null
  dialogVisible.value = true
}

/** 打开编辑弹窗（与详情页「查看详情」是同一个组件）。 */
function openEdit(activity: ActivityOut): void {
  editingActivity.value = activity
  dialogVisible.value = true
}

/** 删除活动（仅所有者，后端校验）。 */
async function remove(activity: ActivityOut): Promise<void> {
  try {
    await activitiesApi.remove(activity.id)
    ElMessage.success('已删除')
    await loadActivities()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '删除失败')
  }
}

/** 时间戳转中文日期展示。 */
function formatDate(value: string | null): string {
  if (!value) return '未定时间'
  return new Date(value).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
}

/** 搜索词变化必须回到第 1 页，否则会停在越界页看到空表。 */
watch(search, () => {
  page.value = 1
  void loadActivities()
})

onMounted(async () => {
  await Promise.all([loadContacts(), loadActivities()])
})
</script>

<template>
  <div class="crm-page">
    <header class="crm-page-head">
      <div>
        <h1 class="crm-page-title crm-display">活 动</h1>
        <p class="crm-page-sub">共 {{ total }} 次 · 和谁、在哪、什么时候</p>
      </div>
      <el-button type="primary" @click="openCreate">记一次活动</el-button>
    </header>

    <div class="crm-toolbar">
      <el-input
        v-model="search"
        placeholder="搜索标题、地点…"
        clearable
        class="crm-search"
      />
    </div>

    <el-table
      v-loading="loading"
      :data="activities"
      class="roster-table"
      empty-text="还没有活动记录"
    >
      <el-table-column label="时间" width="120">
        <template #default="{ row }">{{ formatDate(row.occurred_at) }}</template>
      </el-table-column>
      <el-table-column label="活动" min-width="200">
        <template #default="{ row }">
          <div class="title-line">
            <span class="title">{{ row.title }}</span>
            <el-tag v-if="row.visibility === 'private'" size="small" type="danger">私密</el-tag>
            <el-tag v-if="row.images.length" size="small">{{ row.images.length }} 图</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="地点" min-width="140">
        <template #default="{ row }">{{ row.location || '—' }}</template>
      </el-table-column>
      <el-table-column label="参与者" min-width="220">
        <template #default="{ row }">
          <template v-if="row.participant_ids.length">
            {{ row.participant_ids.length }} 人参与（{{ row.participant_ids.map(nameOf).join('、') }}）
          </template>
          <template v-else>—</template>
        </template>
      </el-table-column>
      <el-table-column prop="owner_display_name" label="记录人" min-width="90" />
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <div @click.stop>
            <el-button text @click="openEdit(row)">编辑</el-button>
            <el-popconfirm :title="`删除「${row.title}」？`" @confirm="remove(row)">
              <template #reference>
                <el-button text type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      :page-size="PAGE_SIZE"
      :total="total"
      layout="prev, pager, next, total"
      class="pager"
      @current-change="loadActivities"
    />

    <ActivityFormDialog
      v-model:visible="dialogVisible"
      :activity="editingActivity"
      @saved="loadActivities"
    />
  </div>
</template>

<style scoped>
.roster-table {
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
}
.title-line {
  display: flex;
  align-items: center;
  gap: 8px;
}
.title {
  font-size: 16px;
  font-weight: 500;
}
.pager {
  margin-top: 14px;
  justify-content: flex-end;
}
</style>
