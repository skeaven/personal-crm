<script setup lang="ts">
/** 名册页：搜索 + 层级过滤 + "最近联系"过滤（主页统计卡跳转联动）+ 名册列表 + 创建抽屉。 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { contactsApi } from '@/api/contacts'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { tokens } from '@/design/tokens'
import ContactAvatar from '@/components/ContactAvatar.vue'
import type { ContactCreate, ContactCreateResponse, ContactOut, DuplicateWarning } from '@/api/types'
import { useFormDirty } from '@/composables/useFormDirty'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

/** "最近联系"过滤（主页统计卡跳转带 ?activity= 进入）。 */
const activityLabels: Record<string, string> = {
  recent_30d: '近 30 天联系过',
  stale_180d: '超过半年未联系',
}
const activityFilter = ref<string>((route.query.activity as string) || '')

/** 清除活动过滤（chip 关闭），同步移除地址栏参数。 */
function clearActivityFilter(): void {
  activityFilter.value = ''
  router.replace({ query: { ...route.query, activity: undefined } })
  loadContacts()
}

/** 创建表单的响应式形状（字面量联合类型保证与契约一致） */
interface CreateForm {
  tier: 'direct' | 'edge'
  last_name: string
  first_name: string
  nickname: string
  gender: NonNullable<ContactCreate['gender']>
  organization: string
  location: string
  bio: string
  visibility: 'private' | 'family'
}

// ---- 列表状态 ----
const loading = ref(false)
const search = ref('')
const tierFilter = ref<'all' | 'direct' | 'edge'>('all')
const contacts = ref<ContactOut[]>([])

const visibleContacts = computed(() =>
  tierFilter.value === 'all'
    ? contacts.value
    : contacts.value.filter((c) => c.tier === tierFilter.value),
)

async function loadContacts(): Promise<void> {
  loading.value = true
  try {
    contacts.value = await contactsApi.list({
      search: search.value || undefined,
      activity: activityFilter.value || undefined,
    })
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) {
      ElMessage.error('名册加载失败')
    }
  } finally {
    loading.value = false
  }
}

// ---- 创建抽屉状态 ----
const showCreate = ref(false)
const creating = ref(false)
const form = ref<CreateForm>({
  tier: 'direct',
  last_name: '',
  first_name: '',
  nickname: '',
  gender: 'unknown',
  organization: '',
  location: '',
  bio: '',
  visibility: 'family',
})
const duplicateWarnings = ref<DuplicateWarning[]>([])

// 名册允许只填名不填姓，与原表单校验一致
const { capture, canSubmit } = useFormDirty(form, {
  isSubmittable: (draft) => draft.last_name.trim().length > 0 || draft.first_name.trim().length > 0,
})

/** 打开创建弹窗：重置为空白表单，避免残留上次取消前的输入。 */
function openCreate(): void {
  resetForm()
  capture()
  showCreate.value = true
}

const genderOptions = [
  { label: '未知', value: 'unknown' },
  { label: '男', value: 'male' },
  { label: '女', value: 'female' },
]

/** 重置创建表单。 */
function resetForm(): void {
  form.value = {
    tier: 'direct',
    last_name: '',
    first_name: '',
    nickname: '',
    gender: 'unknown',
    organization: '',
    location: '',
    bio: '',
    visibility: 'family',
  }
  duplicateWarnings.value = []
}

/** 提交创建；被同名提醒拦截时保留表单并展示警告，用户确认后重发。 */
async function submitCreate(confirmed = false): Promise<void> {
  creating.value = true
  try {
    const payload: ContactCreate = {
      ...form.value,
      nickname: form.value.nickname || null,
      organization: form.value.organization || null,
      location: form.value.location || undefined,
      bio: form.value.bio || null,
      confirm_duplicate: confirmed,
    }
    const result: ContactCreateResponse = await contactsApi.create(payload)
    if (!result.created) {
      duplicateWarnings.value = result.duplicate_warnings
      return
    }
    ElMessage.success(`已记录：${result.contact?.display_name}`)
    showCreate.value = false
    resetForm()
    await loadContacts()
  } catch (error) {
    const text = error instanceof ApiError ? error.message : '创建失败'
    ElMessage.error(text)
  } finally {
    creating.value = false
  }
}

/** 进入联系人详情页（列表行点击的唯一去向，不再使用抽屉）。 */
function openDetail(contact: ContactOut): void {
  router.push({ name: 'contact-detail', params: { id: contact.id } })
}

onMounted(loadContacts)
</script>

<template>
  <div class="crm-page">
    <header class="page-head">
      <div>
        <h1 class="page-title crm-display">名 册</h1>
        <p class="page-sub">共 {{ contacts.length }} 位 · {{ auth.user?.display_name }} 的家庭共享名册</p>
      </div>
      <el-button type="primary" @click="openCreate">记下一个人</el-button>
    </header>

    <div class="toolbar">
      <el-input
        v-model="search"
        placeholder="搜索姓名、昵称…"
        clearable
        class="search"
        @input="loadContacts"
      />
      <el-radio-group v-model="tierFilter">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="direct">直接</el-radio-button>
        <el-radio-button value="edge">边缘</el-radio-button>
      </el-radio-group>
      <!-- naive 的 :color 对象改用 el-tag 的 CSS 变量注入，色值仍取自 tokens -->
      <el-tag
        v-if="activityFilter"
        closable
        size="small"
        :style="{
          '--el-tag-bg-color': tokens.color.sealSoft,
          '--el-tag-text-color': tokens.color.seal,
          '--el-tag-border-color': 'transparent',
        }"
        @close="clearActivityFilter"
      >
        {{ activityLabels[activityFilter] ?? activityFilter }}
      </el-tag>
    </div>

    <el-table
      v-if="visibleContacts.length"
      :data="visibleContacts"
      class="roster-table"
      :row-style="{ cursor: 'pointer' }"
      @row-click="openDetail"
    >
      <el-table-column label="姓名" min-width="220">
        <template #default="{ row }">
          <div class="name-cell">
            <ContactAvatar :name="row.display_name" :size="32" />
            <span class="name-text">{{ row.display_name }}</span>
            <el-tag
              v-if="row.tier === 'edge'"
              size="small"
              :style="{
                '--el-tag-bg-color': tokens.color.bone,
                '--el-tag-text-color': tokens.color.muted,
                '--el-tag-border-color': 'transparent',
              }"
            >
              边缘
            </el-tag>
            <el-tag
              v-if="row.visibility === 'private'"
              size="small"
              :style="{
                '--el-tag-bg-color': tokens.color.sealSoft,
                '--el-tag-text-color': tokens.color.seal,
                '--el-tag-border-color': 'transparent',
              }"
            >
              私密
            </el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="organization" label="单位" min-width="140">
        <template #default="{ row }">{{ row.organization || '—' }}</template>
      </el-table-column>
      <el-table-column prop="owner_display_name" label="记录人" min-width="100" />
    </el-table>
    <!-- naive 的 #extra 插槽对应 el-empty 的默认插槽（渲染在描述下方） -->
    <el-empty v-else-if="!loading" description="名册还是空的，记下第一个重要的人吧" class="empty">
      <el-button type="primary" @click="openCreate">记下一个人</el-button>
    </el-empty>

    <!-- 创建弹窗 -->
    <el-dialog v-model="showCreate" width="480px" title="记下一个人" destroy-on-close>
      <!-- naive 原本即 closable，保留 @close 联动清空重复提醒 -->
      <el-alert
        v-if="duplicateWarnings.length"
        type="warning"
        title="名册里已有相近的人"
        class="dup-alert"
        closable
        @close="duplicateWarnings = []"
      >
        <div v-for="w in duplicateWarnings" :key="w.contact_id" class="dup-item">
          「{{ w.display_name }}」· {{ w.owner_display_name }} 记录
        </div>
        如果确系不同的人，点击「仍要记录」继续。
      </el-alert>

      <el-form label-position="top">
        <el-form-item label="层级">
          <el-radio-group v-model="form.tier">
            <el-radio-button value="direct">直接联系人</el-radio-button>
            <el-radio-button value="edge">边缘联系人</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="姓">
          <el-input v-model="form.last_name" placeholder="如：陈" />
        </el-form-item>
        <el-form-item label="名">
          <el-input v-model="form.first_name" placeholder="如：建国" />
        </el-form-item>
        <el-form-item label="昵称 / 称呼">
          <el-input v-model="form.nickname" placeholder="如：老爸、三婶" />
        </el-form-item>
        <el-form-item label="性别">
          <el-select v-model="form.gender">
            <el-option v-for="opt in genderOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.tier === 'direct'" label="单位">
          <el-input v-model="form.organization" placeholder="选填" />
        </el-form-item>
        <el-form-item label="所在地">
          <el-input v-model="form.location" placeholder="如：上海市浦东新区（保存时自动解析坐标上图）" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.bio" type="textarea" :rows="2" placeholder="一句话简介（选填）" />
        </el-form-item>
        <el-form-item label="家人可见（关闭则仅自己可见）">
          <el-switch v-model="form.visibility" active-value="family" inactive-value="private" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button v-if="duplicateWarnings.length" text @click="resetForm(); showCreate = false">
          取消
        </el-button>
        <el-button
          v-else
          text
          @click="showCreate = false"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="creating"
          :disabled="!canSubmit"
          @click="duplicateWarnings.length ? submitCreate(true) : submitCreate(false)"
        >
          {{ duplicateWarnings.length ? '仍要记录' : '记 下' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 20px;
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
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 10px;
}
.search {
  max-width: 320px;
}
.name-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.name-text {
  font-size: 16px;
}
.roster-table {
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
}
.empty {
  margin-top: 80px;
}
.dup-alert {
  margin-bottom: 14px;
}
.dup-item {
  font-size: 13px;
}
</style>
