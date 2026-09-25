<script setup lang="ts">
/** 礼物往来页：送出/收到记录（搜索 + 方向过滤 + 页码分页）+ 共享表单弹窗。 */
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { giftsApi } from '@/api/gifts'
import { ApiError } from '@/api/client'
import type { GiftDirection, GiftOut } from '@/api/types'
import { useContactOptions } from '@/composables/useContactOptions'
import GiftFormDialog from '@/components/GiftFormDialog.vue'

const { load: loadContacts, nameOf } = useContactOptions()

const PAGE_SIZE = 20
const loading = ref(false)
const search = ref('')
const directionFilter = ref<'all' | GiftDirection>('all')
const gifts = ref<GiftOut[]>([])
const page = ref(1)
const total = ref(0)

const dialogVisible = ref(false)
const editingGift = ref<GiftOut | null>(null)

/** 拉取当前页（后端搜索 + 方向过滤；总数用于页码）。 */
async function loadGifts(): Promise<void> {
  loading.value = true
  try {
    const { items, total: count } = await giftsApi.list({
      search: search.value || undefined,
      direction: directionFilter.value === 'all' ? undefined : directionFilter.value,
      limit: PAGE_SIZE,
      offset: (page.value - 1) * PAGE_SIZE,
    })
    gifts.value = items
    total.value = count
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('礼物记录加载失败')
  } finally {
    loading.value = false
  }
}

/** 打开新建弹窗。 */
function openCreate(): void {
  editingGift.value = null
  dialogVisible.value = true
}

/** 打开编辑弹窗（与详情页往来是同一个组件）。 */
function openEdit(gift: GiftOut): void {
  editingGift.value = gift
  dialogVisible.value = true
}

/** 删除礼物（仅所有者，后端校验）。 */
async function remove(gift: GiftOut): Promise<void> {
  try {
    await giftsApi.remove(gift.id)
    ElMessage.success('已删除')
    await loadGifts()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '删除失败')
  }
}

/** 搜索或方向筛选变化都必须回到第 1 页，否则会停在越界页看到空表。 */
watch([search, directionFilter], () => {
  page.value = 1
  void loadGifts()
})

onMounted(async () => {
  await Promise.all([loadContacts(), loadGifts()])
})
</script>

<template>
  <div class="crm-page">
    <header class="crm-page-head">
      <div>
        <h1 class="crm-page-title crm-display">礼尚往来</h1>
        <p class="crm-page-sub">送出的与收到的，人情都有账</p>
      </div>
      <el-button type="primary" @click="openCreate">记一笔</el-button>
    </header>

    <div class="crm-toolbar">
      <el-input
        v-model="search"
        placeholder="搜索礼物、场合…"
        clearable
        class="crm-search"
      />
      <el-radio-group v-model="directionFilter">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="given">送出</el-radio-button>
        <el-radio-button value="received">收到</el-radio-button>
      </el-radio-group>
    </div>

    <el-table v-loading="loading" :data="gifts" class="roster-table" empty-text="还没有礼物往来">
      <el-table-column label="方向" width="84">
        <template #default="{ row }">
          <el-tag size="small" :type="row.direction === 'given' ? 'info' : 'primary'">
            {{ row.direction === 'given' ? '送出' : '收到' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="礼物" min-width="180">
        <template #default="{ row }">
          <div class="title-line">
            <span class="title">{{ row.title }}</span>
            <el-tag v-if="row.visibility === 'private'" size="small" type="danger">私密</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="110">
        <template #default="{ row }">
          <span v-if="row.amount" class="amount">¥{{ row.amount }}</span>
          <template v-else>—</template>
        </template>
      </el-table-column>
      <el-table-column label="对象" min-width="110">
        <!-- nameOf 对 null 直接返回占位符，无需额外判空 -->
        <template #default="{ row }">{{ nameOf(row.contact_id) }}</template>
      </el-table-column>
      <el-table-column label="场合" min-width="110">
        <template #default="{ row }">{{ row.occasion || '—' }}</template>
      </el-table-column>
      <el-table-column label="日期" width="110">
        <template #default="{ row }">{{ row.given_at || '—' }}</template>
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
      @current-change="loadGifts"
    />

    <GiftFormDialog v-model:visible="dialogVisible" :gift="editingGift" @saved="loadGifts" />
  </div>
</template>

<style scoped>
.pager {
  margin-top: 14px;
  justify-content: flex-end;
}
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
.amount {
  color: var(--crm-ink);
  font-variant-numeric: tabular-nums;
}
.full {
  width: 100%;
}
</style>
