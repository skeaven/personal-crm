<script setup lang="ts">
/** 礼物往来页：送出/收到记录（搜索 + 方向过滤）+ 新建/编辑抽屉。 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { giftsApi } from '@/api/gifts'
import { ApiError } from '@/api/client'
import type { GiftDirection, GiftOut } from '@/api/types'
import { useContactOptions } from '@/composables/useContactOptions'

const { options, load: loadContacts, nameOf } = useContactOptions()

const loading = ref(false)
const search = ref('')
const directionFilter = ref<'all' | GiftDirection>('all')
const gifts = ref<GiftOut[]>([])

/** 拉取礼物列表（后端搜索 + 方向过滤）。 */
async function loadGifts(): Promise<void> {
  loading.value = true
  try {
    gifts.value = await giftsApi.list({
      search: search.value || undefined,
      direction: directionFilter.value === 'all' ? undefined : directionFilter.value,
    })
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('礼物记录加载失败')
  } finally {
    loading.value = false
  }
}

// ---- 抽屉表单 ----
const showDialog = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = ref(emptyForm())

function emptyForm() {
  return {
    direction: 'given' as GiftDirection,
    contact_id: null as number | null,
    title: '',
    occasion: '',
    amount: '',
    given_at: null as string | null,
    link: '',
    description: '',
    visibility: 'family' as 'family' | 'private',
  }
}

function openCreate(): void {
  editingId.value = null
  form.value = emptyForm()
  showDialog.value = true
}

function openEdit(gift: GiftOut): void {
  editingId.value = gift.id
  form.value = {
    direction: gift.direction,
    contact_id: gift.contact_id,
    title: gift.title,
    occasion: gift.occasion ?? '',
    amount: gift.amount ?? '',
    given_at: gift.given_at,
    link: gift.link ?? '',
    description: gift.description ?? '',
    visibility: gift.visibility,
  }
  showDialog.value = true
}

/** 提交：日期选择器以 value-format 直出 YYYY-MM-DD（后端为 DATE 列），金额字符串直传避免浮点误差；
 * 联系人与日期清空后归一为 null（EP 清空产出 undefined，PATCH 缺省键不会清字段）。 */
async function submit(): Promise<void> {
  saving.value = true
  try {
    const payload = {
      direction: form.value.direction,
      contact_id: form.value.contact_id ?? null,
      title: form.value.title,
      occasion: form.value.occasion || null,
      amount: form.value.amount || null,
      given_at: form.value.given_at ?? null,
      link: form.value.link || null,
      description: form.value.description || null,
    }
    if (editingId.value === null) {
      await giftsApi.create(payload)
      ElMessage.success('礼物已记下')
    } else {
      await giftsApi.update(editingId.value, payload)
      ElMessage.success('礼物已更新')
    }
    showDialog.value = false
    await loadGifts()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(gift: GiftOut): Promise<void> {
  try {
    await giftsApi.remove(gift.id)
    ElMessage.success('已删除')
    await loadGifts()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '删除失败')
  }
}

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
        @update:model-value="loadGifts"
      />
      <el-radio-group v-model="directionFilter" @update:model-value="loadGifts">
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

    <el-dialog
      v-model="showDialog"
      width="480px"
      :title="editingId === null ? '记一笔礼物' : '编辑礼物'"
      destroy-on-close
    >
      <el-form label-position="top">
        <el-form-item label="方向">
          <el-radio-group v-model="form.direction">
            <el-radio-button value="given">我送出</el-radio-button>
            <el-radio-button value="received">我收到</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="礼物名称" required>
          <el-input v-model="form.title" placeholder="如：龙井茶" />
        </el-form-item>
        <el-form-item label="对象">
          <el-select v-model="form.contact_id" filterable clearable placeholder="给谁/谁送的">
            <el-option v-for="opt in options" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="场合">
          <el-input v-model="form.occasion" placeholder="生日、婚礼、探病…（选填）" />
        </el-form-item>
        <el-form-item label="金额（元）">
          <el-input v-model="form.amount" placeholder="选填，如 388.00" />
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="form.given_at" type="date" value-format="YYYY-MM-DD" clearable class="full" />
        </el-form-item>
        <el-form-item label="购买/参考链接">
          <el-input v-model="form.link" placeholder="选填" />
        </el-form-item>
        <el-form-item label="礼物说明">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="支持 Markdown（选填）" />
        </el-form-item>
        <el-form-item label="家人可见（关闭则仅自己可见）">
          <el-switch v-model="form.visibility" active-value="family" inactive-value="private" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button text @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="!form.title.trim()" @click="submit">
          保存
        </el-button>
      </template>
    </el-dialog>
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
.amount {
  color: var(--crm-ink);
  font-variant-numeric: tabular-nums;
}
.full {
  width: 100%;
}
</style>
