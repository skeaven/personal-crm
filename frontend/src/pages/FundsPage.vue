<script setup lang="ts">
/** 资金往来页：借贷/礼金流水（多维过滤 + 页码分页 + 结清操作）+ 共享表单弹窗。 */
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { fundsApi } from '@/api/funds'
import { ApiError } from '@/api/client'
import type { FundCategory, FundFlowOut, FundStatus } from '@/api/types'
import { useContactOptions } from '@/composables/useContactOptions'
import FundFormDialog from '@/components/FundFormDialog.vue'

const { load: loadContacts, nameOf } = useContactOptions()

const PAGE_SIZE = 20
const loading = ref(false)
const search = ref('')
const statusFilter = ref<'all' | FundStatus>('all')
const flows = ref<FundFlowOut[]>([])
const page = ref(1)
const total = ref(0)

const dialogVisible = ref(false)
const editingFlow = ref<FundFlowOut | null>(null)

const categoryLabel: Record<FundCategory, string> = {
  loan: '借款',
  repayment: '还款',
  gift_money: '礼金',
  other: '其他',
}

/** 拉取当前页（pending 视图后端按应还日升序；总数用于页码）。 */
async function loadFlows(): Promise<void> {
  loading.value = true
  try {
    const { items, total: count } = await fundsApi.list({
      search: search.value || undefined,
      status: statusFilter.value === 'all' ? undefined : statusFilter.value,
      limit: PAGE_SIZE,
      offset: (page.value - 1) * PAGE_SIZE,
    })
    flows.value = items
    total.value = count
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('资金记录加载失败')
  } finally {
    loading.value = false
  }
}

/** 打开新建弹窗。 */
function openCreate(): void {
  editingFlow.value = null
  dialogVisible.value = true
}

/** 打开编辑弹窗（与详情页往来是同一个组件）。 */
function openEdit(flow: FundFlowOut): void {
  editingFlow.value = flow
  dialogVisible.value = true
}

/** 一键结清/重开（服务端自动维护 settled_at）。 */
async function toggleSettle(flow: FundFlowOut): Promise<void> {
  try {
    await fundsApi.update(flow.id, { status: flow.status === 'settled' ? 'pending' : 'settled' })
    await loadFlows()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '更新失败')
  }
}

/** 删除资金记录（仅所有者，后端校验）。 */
async function remove(flow: FundFlowOut): Promise<void> {
  try {
    await fundsApi.remove(flow.id)
    ElMessage.success('已删除')
    await loadFlows()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '删除失败')
  }
}

/** 应还日是否已过期（未结清且应还日在今天之前）。 */
function isOverdue(flow: FundFlowOut): boolean {
  if (flow.status !== 'pending' || !flow.due_at) return false
  return new Date(flow.due_at).getTime() < Date.now()
}

/** 搜索或状态筛选变化都必须回到第 1 页，否则会停在越界页看到空表。 */
watch([search, statusFilter], () => {
  page.value = 1
  void loadFlows()
})

onMounted(async () => {
  await Promise.all([loadContacts(), loadFlows()])
})
</script>

<template>
  <div class="crm-page">
    <header class="crm-page-head">
      <div>
        <h1 class="crm-page-title crm-display">资金往来</h1>
        <p class="crm-page-sub">借贷、礼金、代付，亲兄弟明算账</p>
      </div>
      <el-button type="primary" @click="openCreate">记一笔</el-button>
    </header>

    <div class="crm-toolbar">
      <el-input
        v-model="search"
        placeholder="搜索说明…"
        clearable
        class="crm-search"
      />
      <el-radio-group v-model="statusFilter">
        <el-radio-button value="pending">未结清</el-radio-button>
        <el-radio-button value="settled">已结清</el-radio-button>
        <el-radio-button value="all">全部</el-radio-button>
      </el-radio-group>
    </div>

    <el-table :data="flows" class="roster-table">
      <el-table-column label="对象" min-width="100">
        <template #default="{ row }">{{ row.contact_id ? nameOf(row.contact_id) : '—' }}</template>
      </el-table-column>
      <!-- 方向 tag 颜色语义与金额列一致：流出红、流入中性 -->
      <el-table-column label="方向" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.direction === 'out' ? 'danger' : 'default'">
            {{ row.direction === 'out' ? '流出' : '流入' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="类别" min-width="120">
        <template #default="{ row }">
          <div class="tag-line">
            <el-tag size="small">{{ categoryLabel[row.category as FundCategory] }}</el-tag>
            <el-tag v-if="row.visibility === 'private'" size="small" type="danger">私密</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="金额" min-width="110" align="right">
        <template #default="{ row }">
          <span class="amount" :class="row.direction">
            {{ row.direction === 'out' ? '−' : '+' }}¥{{ row.amount }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="日期" width="140">
        <template #default="{ row }">
          <div>{{ row.occurred_at }}</div>
          <div v-if="row.due_at" class="due">应还 {{ row.due_at }}</div>
        </template>
      </el-table-column>
      <el-table-column label="说明" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">{{ row.description || '—' }}</template>
      </el-table-column>
      <!-- 状态 tag 可点击切换结清；逾期标记跟在同列 -->
      <el-table-column label="状态" min-width="130">
        <template #default="{ row }">
          <div class="tag-line">
            <el-tag
              v-if="row.status"
              size="small"
              :type="row.status === 'settled' ? 'primary' : 'warning'"
              class="status"
              @click.stop="toggleSettle(row)"
            >
              {{ row.status === 'settled' ? '已结清' : '未结清' }}
            </el-tag>
            <el-tag v-if="isOverdue(row)" size="small" type="danger">已逾期</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="owner_display_name" label="记录人" min-width="80" />
      <el-table-column label="操作" width="140" align="right">
        <template #default="{ row }">
          <el-button text @click.stop="openEdit(row)">编辑</el-button>
          <!-- stop 防触发行级交互；问题文本须走 el-popconfirm 的 title 属性 -->
          <el-popconfirm title="删除这笔记录？" @confirm="remove(row)">
            <template #reference>
              <el-button text type="danger" @click.stop>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      :page-size="PAGE_SIZE"
      :total="total"
      layout="prev, pager, next, total"
      class="pager"
      @current-change="loadFlows"
    />

    <FundFormDialog v-model:visible="dialogVisible" :flow="editingFlow" @saved="loadFlows" />
  </div>
</template>

<style scoped>
.pager {
  margin-top: 14px;
  justify-content: flex-end;
}
/* 表格卡片化：与名册表同一容器质感（底色 + 细线 + 浮动圆角） */
.roster-table {
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
}
.tag-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
/* 金额列颜色语义沿用旧版：流出红（seal）、流入正文色 */
.amount {
  font-size: 16px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap; /* 金额与 +/- 符号同行，避免表格列窄时折行 */
}
.amount.out {
  color: var(--crm-seal);
}
.amount.in {
  color: var(--crm-ink);
}
.due {
  color: var(--crm-muted);
  font-size: 13px;
}
.status {
  cursor: pointer;
}
.full {
  width: 100%;
}
</style>
