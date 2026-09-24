<script setup lang="ts">
/** 待办页：全系统时间义务的统一视图（五来源聚合）+ 手工任务的增改与勾选完成。
 *
 * 四页签：待办（未过期）/ 过期 / 已完成 / 全部；来源徽标区分 任务/心愿/还款/活动/生日。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { dashboardApi } from '@/api/dashboard'
import { tasksApi } from '@/api/records'
import { ApiError } from '@/api/client'
import { tokens } from '@/design/tokens'
import type { TodoBucket, TodoItemOut, TodoSource } from '@/api/types'
import { useContactOptions } from '@/composables/useContactOptions'

const router = useRouter()
const { options, load: loadContacts, nameOf } = useContactOptions()

const loading = ref(false)
const bucket = ref<TodoBucket>('todo')
const todos = ref<TodoItemOut[]>([])

/** 来源徽标文案与配色（seal 红仅用于过期/警示，符合设计规范）。 */
const sourceMeta: Record<TodoSource, { label: string; color: string; textColor: string; to?: string }> = {
  task: { label: '任务', color: tokens.color.bone, textColor: tokens.color.ink, to: '/tasks' },
  wish: { label: '心愿', color: tokens.color.bone, textColor: tokens.color.ink, to: '/wishlist' },
  repayment: { label: '还款', color: tokens.color.sealSoft, textColor: tokens.color.seal, to: '/funds' },
  activity: { label: '活动', color: tokens.color.bone, textColor: tokens.color.ink, to: '/activities' },
  birthday: { label: '生日', color: tokens.color.sealSoft, textColor: tokens.color.seal },
}

/** 拉取聚合待办（后端分桶与排序）。 */
async function loadTodos(): Promise<void> {
  loading.value = true
  try {
    todos.value = await dashboardApi.todos(bucket.value)
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('待办加载失败')
  } finally {
    loading.value = false
  }
}

/** 过期桶里的剩余数量（页签徽标提示，待办视角的关注点）。 */
const overdueCount = computed(() => todos.value.filter((item) => item.bucket === 'overdue').length)

/** 剩余天数的文案：今天/还剩 N 天/已过期 N 天；生日显示农历标签。 */
function dueLabel(item: TodoItemOut): { text: string; urgent: boolean } {
  if (item.days_left === null) return { text: '', urgent: false }
  if (item.days_left === 0) return { text: '就是今天', urgent: true }
  if (item.days_left > 0) return { text: `还剩 ${item.days_left} 天`, urgent: item.days_left <= 3 }
  return { text: `已过期 ${-item.days_left} 天`, urgent: true }
}

/** 勾选/取消完成（仅手工任务有此操作；其他来源的状态由各自模块管理）。 */
async function toggleDone(item: TodoItemOut, done: boolean): Promise<void> {
  try {
    await tasksApi.update(item.ref_id, { status: done ? 'done' : 'todo' })
    await loadTodos()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '更新失败')
  }
}

/** 点击待办项跳转：生日→联系人详情，其余按来源页跳转。 */
function open(item: TodoItemOut): void {
  if (item.source === 'birthday' && item.contact_id) {
    router.push({ name: 'contact-detail', params: { id: item.contact_id } })
    return
  }
  const target = sourceMeta[item.source].to
  if (target) router.push(target)
}

// ---- 手工任务抽屉（新建/编辑，仅 task 源） ----
const showDrawer = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = ref(emptyForm())

function emptyForm() {
  return {
    title: '',
    contact_id: null as number | null,
    due_at: null as string | null,
    detail: '',
    visibility: 'family' as 'family' | 'private',
  }
}

function openCreate(): void {
  editingId.value = null
  form.value = emptyForm()
  showDrawer.value = true
}

/** 从聚合项打开编辑（仅 task 源会出现编辑按钮）。 */
function openEditFromTodo(item: TodoItemOut): void {
  editingId.value = item.ref_id
  form.value = {
    title: item.title,
    contact_id: item.contact_id,
    due_at: item.due_date ? `${item.due_date} 12:00` : null,
    detail: '',
    visibility: 'family',
  }
  showDrawer.value = true
}

async function submit(): Promise<void> {
  saving.value = true
  try {
    const payload = {
      title: form.value.title,
      // 联系人清空后归一为 null（EP 清空产出 undefined，PATCH 缺省键不会清字段）
      contact_id: form.value.contact_id ?? null,
      // value-format 产出 "YYYY-MM-DD HH:mm"，空格换 T 才能被 Date 按本地时区解析（正午时刻防时区偏移）
      due_at: form.value.due_at ? new Date(form.value.due_at.replace(' ', 'T')).toISOString() : null,
      detail: form.value.detail || null,
    }
    if (editingId.value === null) {
      await tasksApi.create(payload)
      ElMessage.success('待办已记录')
    } else {
      await tasksApi.update(editingId.value, payload)
      ElMessage.success('待办已更新')
    }
    showDrawer.value = false
    await loadTodos()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

/** 删除手工任务（事件冒泡已阻断，不触发行跳转）。 */
async function removeTask(item: TodoItemOut): Promise<void> {
  try {
    await tasksApi.remove(item.ref_id)
    ElMessage.success('已删除')
    await loadTodos()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '删除失败')
  }
}

function formatDate(value: string | null): string {
  if (!value) return ''
  return new Date(`${value}T12:00:00`).toLocaleDateString('zh-CN')
}

onMounted(async () => {
  await Promise.all([loadContacts(), loadTodos()])
})
</script>

<template>
  <div class="crm-page">
    <header class="crm-page-head">
      <div>
        <h1 class="crm-page-title crm-display">待 办</h1>
        <p class="crm-page-sub">任务、心愿、还款、活动、生日，都在这里</p>
      </div>
      <el-button type="primary" @click="openCreate">记一件事</el-button>
    </header>

    <div class="crm-toolbar">
      <el-radio-group v-model="bucket" @update:model-value="loadTodos">
        <el-radio-button value="todo">待办</el-radio-button>
        <el-radio-button value="overdue">过期</el-radio-button>
        <el-radio-button value="done">已完成</el-radio-button>
        <el-radio-button value="all">全部</el-radio-button>
      </el-radio-group>
      <span v-if="bucket === 'overdue' && todos.length" class="overdue-hint">
        过期不等于结束——补个祝福、催一笔款，都还来得及
      </span>
    </div>

    <el-table
      v-loading="loading"
      :data="todos"
      class="roster-table"
      :row-style="{ cursor: 'pointer' }"
      :empty-text="bucket === 'overdue' ? '没有过期的事，很体面' : '没有待办，世界清净'"
      @row-click="open"
    >
      <el-table-column width="46">
        <template #default="{ row }">
          <el-checkbox
            v-if="row.source === 'task'"
            :model-value="row.bucket === 'done'"
            @click.stop
            @update:model-value="(checked: boolean) => toggleDone(row, checked)"
          />
        </template>
      </el-table-column>
      <el-table-column label="来源" width="84">
        <template #default="{ row }">
          <el-tag
            size="small"
            :style="{
              backgroundColor: sourceMeta[row.source as TodoSource].color,
              color: sourceMeta[row.source as TodoSource].textColor,
            }"
          >
            {{ sourceMeta[row.source as TodoSource].label }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="事项" min-width="280">
        <template #default="{ row }">
          <div class="title-line">
            <span class="title" :class="{ done: row.bucket === 'done' }">{{ row.title }}</span>
            <span v-if="row.lunar_label" class="lunar">{{ row.lunar_label }}</span>
          </div>
          <div class="meta">
            <template v-if="row.due_date">{{ formatDate(row.due_date) }}</template>
            <template v-if="dueLabel(row).text">
              · <span :class="{ urgent: dueLabel(row).urgent }">{{ dueLabel(row).text }}</span>
            </template>
            <template v-if="row.contact_name && row.source !== 'birthday' && row.source !== 'task'">
              · {{ row.contact_name }}
            </template>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <div v-if="row.source === 'task'" @click.stop>
            <el-button text @click="openEditFromTodo(row)">编辑</el-button>
            <el-popconfirm :title="`删除「${row.title}」？`" @confirm="removeTask(row)">
              <template #reference>
                <el-button text type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <el-drawer v-model="showDrawer" size="420px" :title="editingId === null ? '记一件事' : '编辑待办'">
      <el-form label-position="top">
        <el-form-item label="事项" required>
          <el-input v-model="form.title" placeholder="如：给老爸买生日礼物" />
        </el-form-item>
        <el-form-item label="关联联系人">
          <el-select v-model="form.contact_id" filterable clearable placeholder="选填">
            <el-option v-for="opt in options" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="截止时间">
          <el-date-picker
            v-model="form.due_at"
            type="datetime"
            value-format="YYYY-MM-DD HH:mm"
            clearable
            class="full"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.detail" type="textarea" :rows="2" placeholder="选填" />
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
.title.done {
  color: var(--crm-muted);
  text-decoration: line-through;
}
.lunar {
  color: var(--crm-muted);
  font-size: 13px;
}
.meta {
  color: var(--crm-muted);
  font-size: 13px;
  margin-top: 2px;
}
.meta :deep(.urgent),
.urgent {
  color: var(--crm-seal);
}
.full {
  width: 100%;
}
.overdue-hint {
  color: var(--crm-muted);
  font-size: 13px;
  align-self: center;
}
</style>
