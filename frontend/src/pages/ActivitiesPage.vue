<script setup lang="ts">
/** 活动页：社交活动列表（搜索）+ 新建/编辑抽屉（时间/地点/参与者多选）。 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { activitiesApi } from '@/api/records'
import { ApiError } from '@/api/client'
import type { ActivityOut } from '@/api/types'
import { useContactOptions } from '@/composables/useContactOptions'

const { options, load: loadContacts, nameOf } = useContactOptions()

const loading = ref(false)
const search = ref('')
const activities = ref<ActivityOut[]>([])

/** 拉取活动列表（标题/地点关键字搜索由后端执行）。 */
async function loadActivities(): Promise<void> {
  loading.value = true
  try {
    activities.value = await activitiesApi.list({ search: search.value || undefined })
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('活动加载失败')
  } finally {
    loading.value = false
  }
}

// ---- 抽屉表单（新建与编辑共用） ----
const showDrawer = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = ref(emptyForm())

function emptyForm() {
  return {
    title: '',
    occurred_at: null as number | null,
    location: '',
    detail: '',
    participant_ids: [] as number[],
    visibility: 'family' as 'family' | 'private',
  }
}

/** 打开新建抽屉（清空表单）。 */
function openCreate(): void {
  editingId.value = null
  form.value = emptyForm()
  showDrawer.value = true
}

/** 打开编辑抽屉（回填活动数据；时间转时间戳供日期控件使用）。 */
function openEdit(activity: ActivityOut): void {
  editingId.value = activity.id
  form.value = {
    title: activity.title,
    occurred_at: activity.occurred_at ? new Date(activity.occurred_at).getTime() : null,
    location: activity.location ?? '',
    detail: activity.detail ?? '',
    participant_ids: [...activity.participant_ids],
    visibility: activity.visibility,
  }
  showDrawer.value = true
}

/** 提交表单：时间戳转 ISO 后按新建/编辑分流。 */
async function submit(): Promise<void> {
  saving.value = true
  try {
    const payload = {
      title: form.value.title,
      occurred_at: form.value.occurred_at ? new Date(form.value.occurred_at).toISOString() : null,
      location: form.value.location || null,
      detail: form.value.detail || null,
      participant_ids: form.value.participant_ids,
    }
    if (editingId.value === null) {
      await activitiesApi.create(payload)
      ElMessage.success('活动已记录')
    } else {
      await activitiesApi.update(editingId.value, payload)
      ElMessage.success('活动已更新')
    }
    showDrawer.value = false
    await loadActivities()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
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

onMounted(async () => {
  await Promise.all([loadContacts(), loadActivities()])
})
</script>

<template>
  <div class="crm-page">
    <header class="crm-page-head">
      <div>
        <h1 class="crm-page-title crm-display">活 动</h1>
        <p class="crm-page-sub">共 {{ activities.length }} 次 · 和谁、在哪、什么时候</p>
      </div>
      <el-button type="primary" @click="openCreate">记一次活动</el-button>
    </header>

    <div class="crm-toolbar">
      <el-input
        v-model="search"
        placeholder="搜索标题、地点…"
        clearable
        class="crm-search"
        @input="loadActivities"
      />
    </div>

    <el-table v-loading="loading" :data="activities" class="roster-table" empty-text="还没有活动记录">
      <el-table-column label="时间" width="120">
        <template #default="{ row }">{{ formatDate(row.occurred_at) }}</template>
      </el-table-column>
      <el-table-column label="活动" min-width="200">
        <template #default="{ row }">
          <div class="title-line">
            <span class="title">{{ row.title }}</span>
            <el-tag v-if="row.visibility === 'private'" size="small" type="danger">私密</el-tag>
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

    <el-drawer
      v-model="showDrawer"
      size="440px"
      direction="rtl"
      :title="editingId === null ? '记一次活动' : '编辑活动'"
      :show-close="true"
    >
      <el-form label-position="top">
        <el-form-item label="标题" required>
          <el-input v-model="form.title" placeholder="如：家庭团圆饭" />
        </el-form-item>
        <el-form-item label="时间">
          <!-- value-format="x"：模型保持毫秒时间戳（number），与原 n-date-picker 语义一致 -->
          <el-date-picker v-model="form.occurred_at" type="datetime" value-format="x" clearable class="full" />
        </el-form-item>
        <el-form-item label="地点">
          <el-input v-model="form.location" placeholder="选填" />
        </el-form-item>
        <el-form-item label="参与的人">
          <el-select
            v-model="form.participant_ids"
            multiple
            filterable
            placeholder="从名册选择（可多选）"
          >
            <el-option v-for="opt in options" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="详情">
          <el-input v-model="form.detail" type="textarea" :rows="3" placeholder="发生了什么、聊了什么（选填）" />
        </el-form-item>
        <el-form-item label="家人可见（关闭则仅自己可见）">
          <el-switch v-model="form.visibility" active-value="family" inactive-value="private" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="crm-drawer-footer">
          <el-button text @click="showDrawer = false">取消</el-button>
          <el-button type="primary" :loading="saving" :disabled="!form.title.trim()" @click="submit">
            保存
          </el-button>
        </div>
      </template>
    </el-drawer>
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
.full {
  width: 100%;
}
</style>
