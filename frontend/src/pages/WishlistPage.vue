<script setup lang="ts">
/** 愿望清单页：还没送出的礼物（状态过滤 + 一键转礼物）。 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { wishlistApi } from '@/api/gifts'
import { ApiError } from '@/api/client'
import type { WishlistOut, WishlistStatus } from '@/api/types'
import { useContactOptions } from '@/composables/useContactOptions'

const { options, load: loadContacts, nameOf } = useContactOptions()

const loading = ref(false)
const search = ref('')
const statusFilter = ref<'all' | WishlistStatus>('open')
const items = ref<WishlistOut[]>([])

const statusLabel: Record<WishlistStatus, string> = {
  open: '想送',
  purchased: '已购买',
  given: '已送出',
}

/** 拉取愿望列表。 */
async function loadItems(): Promise<void> {
  loading.value = true
  try {
    items.value = await wishlistApi.list({
      search: search.value || undefined,
      status: statusFilter.value === 'all' ? undefined : statusFilter.value,
    })
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('愿望清单加载失败')
  } finally {
    loading.value = false
  }
}

// ---- 抽屉表单 ----
const showDrawer = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = ref(emptyForm())

function emptyForm() {
  return {
    contact_id: null as number | null,
    title: '',
    amount: '',
    target_date: null as string | null,
    link: '',
    description: '',
    visibility: 'family' as 'family' | 'private',
  }
}

function openCreate(): void {
  editingId.value = null
  form.value = emptyForm()
  showDrawer.value = true
}

function openEdit(item: WishlistOut): void {
  editingId.value = item.id
  form.value = {
    contact_id: item.contact_id,
    title: item.title,
    amount: item.amount ?? '',
    target_date: item.target_date,
    link: item.link ?? '',
    description: item.description ?? '',
    visibility: item.visibility,
  }
  showDrawer.value = true
}

async function submit(): Promise<void> {
  saving.value = true
  try {
    const payload = {
      contact_id: form.value.contact_id,
      title: form.value.title,
      amount: form.value.amount || null,
      target_date: form.value.target_date,
      link: form.value.link || null,
      description: form.value.description || null,
    }
    if (editingId.value === null) {
      await wishlistApi.create(payload)
      ElMessage.success('愿望已记下')
    } else {
      await wishlistApi.update(editingId.value, payload)
      ElMessage.success('愿望已更新')
    }
    showDrawer.value = false
    await loadItems()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

/** 愿望送出 → 生成礼物记录并闭环（后端幂等保护）。 */
async function convert(item: WishlistOut): Promise<void> {
  try {
    const result = await wishlistApi.convert(item.id)
    ElMessage.success(`已转成送出记录「${result.gift.title}」`)
    await loadItems()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '转换失败')
  }
}

async function remove(item: WishlistOut): Promise<void> {
  try {
    await wishlistApi.remove(item.id)
    ElMessage.success('已删除')
    await loadItems()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '删除失败')
  }
}

onMounted(async () => {
  await Promise.all([loadContacts(), loadItems()])
})
</script>

<template>
  <div class="crm-page">
    <header class="crm-page-head">
      <div>
        <h1 class="crm-page-title crm-display">心愿单</h1>
        <p class="crm-page-sub">想送还没送的，别错过日子</p>
      </div>
      <el-button type="primary" @click="openCreate">加一个心愿</el-button>
    </header>

    <div class="crm-toolbar">
      <el-input
        v-model="search"
        placeholder="搜索心愿…"
        clearable
        class="crm-search"
        @update:model-value="loadItems"
      />
      <el-radio-group v-model="statusFilter" @update:model-value="loadItems">
        <el-radio-button value="open">想送</el-radio-button>
        <el-radio-button value="purchased">已购买</el-radio-button>
        <el-radio-button value="given">已送出</el-radio-button>
        <el-radio-button value="all">全部</el-radio-button>
      </el-radio-group>
    </div>

    <el-table :data="items" class="roster-table">
      <el-table-column label="心愿" min-width="170">
        <template #default="{ row }">
          <div class="title-cell">
            <span class="title">{{ row.title }}</span>
            <el-tag v-if="row.visibility === 'private'" size="small" type="danger">私密</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="对象" min-width="100">
        <template #default="{ row }">{{ row.contact_id ? nameOf(row.contact_id) : '—' }}</template>
      </el-table-column>
      <el-table-column label="预估金额" min-width="110" align="right">
        <template #default="{ row }">
          <span v-if="row.amount" class="amount">¥{{ row.amount }}</span>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="目标日期" width="110">
        <template #default="{ row }">{{ row.target_date || '—' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag
            size="small"
            :type="row.status === 'given' ? 'primary' : row.status === 'purchased' ? 'info' : 'default'"
          >
            {{ statusLabel[row.status as WishlistStatus] }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="owner_display_name" label="记录人" min-width="90" />
      <el-table-column label="操作" width="200" align="right">
        <template #default="{ row }">
          <el-button v-if="row.status !== 'given'" text type="primary" @click.stop="convert(row)">
            送出了
          </el-button>
          <el-button text @click.stop="openEdit(row)">编辑</el-button>
          <!-- stop 防触发行级交互；问题文本须走 el-popconfirm 的 title 属性 -->
          <el-popconfirm :title="`删除「${row.title}」？`" @confirm="remove(row)">
            <template #reference>
              <el-button text type="danger" @click.stop>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-drawer
      v-model="showDrawer"
      size="440px"
      direction="rtl"
      :title="editingId === null ? '加一个心愿' : '编辑心愿'"
    >
      <el-form label-position="top">
        <el-form-item label="想送的礼物" required>
          <el-input v-model="form.title" placeholder="如：按摩仪" />
        </el-form-item>
        <el-form-item label="为谁准备">
          <el-select v-model="form.contact_id" filterable clearable placeholder="从名册选择">
            <el-option
              v-for="opt in options"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="预算/价格（元）">
          <el-input v-model="form.amount" placeholder="选填，如 599.00" />
        </el-form-item>
        <el-form-item label="打算送出的日期">
          <el-date-picker
            v-model="form.target_date"
            type="date"
            value-format="YYYY-MM-DD"
            clearable
            class="full"
          />
        </el-form-item>
        <el-form-item label="购买链接">
          <el-input v-model="form.link" placeholder="选填" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="支持 Markdown（选填）" />
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
/* 表格卡片化：与名册表同一容器质感（底色 + 细线 + 浮动圆角） */
.roster-table {
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
}
.title-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}
.title {
  font-size: 16px;
  font-weight: 500;
}
.amount {
  font-variant-numeric: tabular-nums;
}
.full {
  width: 100%;
}
</style>
