<script setup lang="ts">
/** 资金往来页：借贷/礼金流水（多维过滤 + 结清操作）。 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fundsApi } from '@/api/funds'
import { ApiError } from '@/api/client'
import type { FundCategory, FundDirection, FundFlowOut, FundStatus } from '@/api/types'
import { useContactOptions } from '@/composables/useContactOptions'

const { options, load: loadContacts, nameOf } = useContactOptions()

const loading = ref(false)
const search = ref('')
const statusFilter = ref<'all' | FundStatus>('all')
const flows = ref<FundFlowOut[]>([])

const categoryLabel: Record<FundCategory, string> = {
  loan: '借款',
  repayment: '还款',
  gift_money: '礼金',
  other: '其他',
}

/** 拉取资金流水（pending 视图后端按应还日升序）。 */
async function loadFlows(): Promise<void> {
  loading.value = true
  try {
    flows.value = await fundsApi.list({
      search: search.value || undefined,
      status: statusFilter.value === 'all' ? undefined : statusFilter.value,
    })
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('资金记录加载失败')
  } finally {
    loading.value = false
  }
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

// ---- 抽屉表单 ----
const showDialog = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = ref(emptyForm())

function emptyForm() {
  return {
    direction: 'out' as FundDirection,
    category: 'loan' as FundCategory,
    contact_id: null as number | null,
    amount: '',
    occurred_at: null as string | null,
    due_at: null as string | null,
    description: '',
    visibility: 'family' as 'family' | 'private',
  }
}

function openCreate(): void {
  editingId.value = null
  form.value = emptyForm()
  showDialog.value = true
}

function openEdit(flow: FundFlowOut): void {
  editingId.value = flow.id
  form.value = {
    direction: flow.direction,
    category: flow.category,
    contact_id: flow.contact_id,
    amount: flow.amount,
    occurred_at: flow.occurred_at,
    due_at: flow.due_at,
    description: flow.description ?? '',
    visibility: flow.visibility,
  }
  showDialog.value = true
}

async function submit(): Promise<void> {
  if (!form.value.occurred_at) {
    ElMessage.error('请选择发生日期')
    return
  }
  saving.value = true
  try {
    const payload = {
      direction: form.value.direction,
      category: form.value.category,
      contact_id: form.value.contact_id,
      amount: form.value.amount,
      occurred_at: form.value.occurred_at as string,
      due_at: form.value.due_at,
      description: form.value.description || null,
    }
    if (editingId.value === null) {
      await fundsApi.create(payload)
      ElMessage.success('资金记录已记下')
    } else {
      await fundsApi.update(editingId.value, payload)
      ElMessage.success('资金记录已更新')
    }
    showDialog.value = false
    await loadFlows()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

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
        @update:model-value="loadFlows"
      />
      <el-radio-group v-model="statusFilter" @update:model-value="loadFlows">
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

    <el-dialog
      v-model="showDialog"
      width="480px"
      :title="editingId === null ? '记一笔资金往来' : '编辑记录'"
      destroy-on-close
    >
      <el-form label-position="top">
        <el-form-item label="方向">
          <el-radio-group v-model="form.direction">
            <el-radio-button value="out">流出（借出/支出）</el-radio-button>
            <el-radio-button value="in">流入（借入/收到）</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="类别">
          <el-radio-group v-model="form.category">
            <el-radio-button value="loan">借款</el-radio-button>
            <el-radio-button value="repayment">还款</el-radio-button>
            <el-radio-button value="gift_money">礼金</el-radio-button>
            <el-radio-button value="other">其他</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="对象联系人">
          <el-select v-model="form.contact_id" filterable clearable placeholder="选填">
            <el-option
              v-for="opt in options"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="金额（元）" required>
          <el-input v-model="form.amount" placeholder="如 2000.00" />
        </el-form-item>
        <el-form-item label="发生日期" required>
          <el-date-picker
            v-model="form.occurred_at"
            type="date"
            value-format="YYYY-MM-DD"
            class="full"
          />
        </el-form-item>
        <el-form-item label="应收/应还日（借贷类填写后自动进入未结清）">
          <el-date-picker
            v-model="form.due_at"
            type="date"
            value-format="YYYY-MM-DD"
            clearable
            class="full"
          />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="选填" />
        </el-form-item>
        <el-form-item label="家人可见（关闭则仅自己可见）">
          <el-switch v-model="form.visibility" active-value="family" inactive-value="private" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button text @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="!form.amount.trim()" @click="submit">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
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
