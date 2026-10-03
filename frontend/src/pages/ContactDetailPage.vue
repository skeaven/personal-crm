<script setup lang="ts">
/** 联系人详情页：系统的核心枢纽。
 * 结构 = 头部 + 静态区（基本信息/重要日期/关系，两列瀑布排布）
 *       + 往来区（活动/资金/礼物三个 Tab，各自分页加载，D19）。
 * 每个 Tab 由 RecordTimeline 独立取数与渲染，保存/删除后按记录所属 Tab 刷新；
 * 新增往来类型时加一个 Tab 与对应共享弹窗即可，不需要动 dashboard 的聚合接口
 * （那个保留给 AI 工具的 get_contact_timeline）。 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { contactsApi } from '@/api/contacts'
import { graphApi } from '@/api/graph'
import { activitiesApi } from '@/api/records'
import { giftsApi } from '@/api/gifts'
import { fundsApi } from '@/api/funds'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { tokens } from '@/design/tokens'
import { toDateInput } from '@/utils/datetime'
import ContactAvatar from '@/components/ContactAvatar.vue'
import RecordTimeline from '@/components/RecordTimeline.vue'
import ActivityFormDialog from '@/components/ActivityFormDialog.vue'
import GiftFormDialog from '@/components/GiftFormDialog.vue'
import FundFormDialog from '@/components/FundFormDialog.vue'
import type {
  ContactDetailOut,
  ImportantDateCreate,
  ImportantDateOut,
  RelationshipOut,
  RelationshipTypeOut,
  TimelineRecord,
  TimelineSource,
} from '@/api/types'
import type { ActivityOut, FundFlowOut, GiftOut } from '@/api/types'
import { ROLE_DOMAINS, ROLE_LABELS } from '@/api/types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const contact = ref<ContactDetailOut | null>(null)
const loading = ref(true)
const saving = ref(false)

const contactId = computed(() => Number(route.params.id))
const isOwned = computed(() => contact.value?.owner_user_id === auth.user?.id)

/** 性别下拉选项（编辑资料表单用，与名册表单同源语义）。 */
const genderOptions: { label: string; value: 'male' | 'female' | 'other' | 'unknown' }[] = [
  { label: '男', value: 'male' },
  { label: '女', value: 'female' },
  { label: '其他', value: 'other' },
  { label: '未知', value: 'unknown' },
]

// ---- 编辑资料弹窗（D16：官方组件形态优先）——全字段 el-dialog + el-form ----
const showEditDialog = ref(false)
const editSaving = ref(false)
interface EditDraft {
  name: string
  nickname: string
  gender: 'male' | 'female' | 'other' | 'unknown'
  organization: string
  location: string
  bio: string
}
const editDraft = ref<EditDraft>({
  name: '',
  nickname: '',
  gender: 'unknown',
  organization: '',
  location: '',
  bio: '',
})

/** 打开编辑弹窗：以当前联系人全量字段回填草稿。 */
function openEdit(): void {
  const c = contact.value
  if (!c) return
  editDraft.value = {
    name: c.name,
    nickname: c.nickname ?? '',
    gender: c.gender,
    organization: c.organization ?? '',
    location: c.location ?? '',
    bio: c.bio ?? '',
  }
  showEditDialog.value = true
}

/** 提交编辑：PATCH 全字段，成功后刷新详情（所在地坐标由服务端重算）。 */
async function submitEdit(): Promise<void> {
  if (!contact.value) return
  editSaving.value = true
  try {
    contact.value = await contactsApi.update(contact.value.id, {
      name: editDraft.value.name,
      nickname: editDraft.value.nickname || null,
      gender: editDraft.value.gender,
      organization: editDraft.value.organization || null,
      location: editDraft.value.location || null,
      bio: editDraft.value.bio || null,
    })
    ElMessage.success('资料已更新')
    showEditDialog.value = false
    await loadRelations()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    editSaving.value = false
  }
}

const genderLabel: Record<string, string> = { male: '男', female: '女', other: '其他', unknown: '未知' }

// ---- 重要日期编辑状态（仅所有者可见操作） ----
const dateTableRef = ref()
const relationTableRef = ref()
const showDateForm = ref(false)
const dateSaving = ref(false)
const editingDateId = ref<number | null>(null)
const dateDraft = ref(emptyDateDraft())

function emptyDateDraft() {
  return {
    type: 'birthday' as 'birthday' | 'anniversary' | 'memorial' | 'other',
    title: '',
    calendar: 'solar' as 'solar' | 'lunar',
    solar_ts: null as Date | null,
    lunar_month: 1,
    lunar_day: 1,
    lunar_is_leap: false,
    leads: [7, 1] as number[],
  }
}

const dateTypeOptions = [
  { label: '生日', value: 'birthday' },
  { label: '纪念日', value: 'anniversary' },
  { label: '其他', value: 'other' },
]
/** 历法下拉选项（原 n-select 内联字面量，改写为 el-select 的选项常量数组）。 */
const calendarOptions: { label: string; value: 'solar' | 'lunar' }[] = [
  { label: '公历', value: 'solar' },
  { label: '农历', value: 'lunar' },
]
const leadOptions = [1, 3, 7, 15, 30].map((days) => ({ label: `${days} 天`, value: days }))
const lunarMonthOptions = ['正', '二', '三', '四', '五', '六', '七', '八', '九', '十', '冬', '腊'].map(
  (name, index) => ({ label: `${name}月`, value: index + 1 }),
)
const lunarDayOptions = Array.from({ length: 30 }, (_, index) => {
  const day = index + 1
  const ones = '一二三四五六七八九'
  const name =
    day === 10 ? '初十' : day === 20 ? '二十' : day === 30 ? '三十' : day < 10 ? `初${ones[day - 1]}` : day < 20 ? `十${ones[day - 11]}` : `廿${ones[day - 21]}`
  return { label: name, value: day }
})

/** 农历日期的中文展示（与后端 calendar.py 口径一致的轻量前端映射）。 */
function lunarLabel(month: number, day: number, isLeap: boolean): string {
  const monthName = ['正', '二', '三', '四', '五', '六', '七', '八', '九', '十', '冬', '腊'][month - 1] ?? `${month}`
  const ones = '一二三四五六七八九'
  const dayName =
    day === 10
      ? '初十'
      : day === 20
        ? '二十'
        : day === 30
          ? '三十'
          : day < 10
            ? `初${ones[day - 1]}`
            : day < 20
              ? `十${ones[day - 11]}`
              : `廿${ones[day - 21]}`
  return `农历${isLeap ? '闰' : ''}${monthName}月${dayName}`
}

/** 日期行文案（重要日期区块）。 */
function dateLine(d: ImportantDateOut): string {
  const typeLabel = d.type === 'birthday' ? '生日' : d.type === 'anniversary' ? '纪念日' : '纪念日'
  const title = d.title ? `${d.title} · ` : ''
  const when =
    d.calendar === 'solar'
      ? `公历 ${d.date_solar ?? '未设置'}`
      : lunarLabel(d.lunar_month ?? 1, d.lunar_day ?? 1, d.lunar_is_leap)
  return `${title}${typeLabel} · ${when}`
}

function openDateCreate(): void {
  editingDateId.value = null
  dateDraft.value = emptyDateDraft()
  showDateForm.value = true
}

/** 打开编辑：公历回填日期对象（取当日正午防时区偏移），农历回填月日。 */
function openDateEdit(d: ImportantDateOut): void {
  editingDateId.value = d.id
  dateDraft.value = {
    type: d.type,
    title: d.title ?? '',
    calendar: d.calendar,
    solar_ts: d.date_solar ? new Date(`${d.date_solar}T12:00:00`) : null,
    lunar_month: d.lunar_month ?? 1,
    lunar_day: d.lunar_day ?? 1,
    lunar_is_leap: d.lunar_is_leap,
    leads: [...d.reminder_lead_days],
  }
  showDateForm.value = true
}

/** 提交日期（新建/编辑分流），成功后以返回的详情刷新整页数据。 */
async function submitDate(): Promise<void> {
  if (!contact.value) return
  dateSaving.value = true
  try {
    const draft = dateDraft.value
    const payload: ImportantDateCreate = {
      type: draft.type,
      title: draft.title || null,
      calendar: draft.calendar,
      yearly: true,
      reminder_lead_days: draft.leads,
      ...(draft.calendar === 'solar'
        ? {
            date_solar: draft.solar_ts
              ? toDateInput(draft.solar_ts.getTime())
              : null,
          }
        : {
            lunar_month: draft.lunar_month,
            lunar_day: draft.lunar_day,
            lunar_is_leap: draft.lunar_is_leap,
          }),
    }
    contact.value =
      editingDateId.value === null
        ? await contactsApi.createDate(contact.value.id, payload)
        : await contactsApi.updateDate(contact.value.id, editingDateId.value, payload)
    ElMessage.success(editingDateId.value === null ? '日期已记录' : '日期已更新')
    showDateForm.value = false
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    dateSaving.value = false
  }
}

async function removeDate(d: ImportantDateOut): Promise<void> {
  if (!contact.value) return
  try {
    await contactsApi.removeDate(contact.value.id, d.id)
    ElMessage.success('已删除')
    await loadContact()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '删除失败')
  }
}

// ---- 往来 Tabs：每类各自分页加载，不再依赖 dashboard 聚合接口 ----
const activeTab = ref<TimelineSource>('activity')
const timelineRefs = ref<Record<string, { reload: () => Promise<void> } | null>>({})

// 三源共用的表单弹窗（与列表页是同一个组件，行为一致）
const activityDialogVisible = ref(false)
const editingActivity = ref<ActivityOut | null>(null)
const giftDialogVisible = ref(false)
const editingGift = ref<GiftOut | null>(null)
const fundDialogVisible = ref(false)
const editingFlow = ref<FundFlowOut | null>(null)

/** 打开活动新建弹窗。 */
function openNewActivity(): void {
  editingActivity.value = null
  activityDialogVisible.value = true
}

/** 打开资金新建弹窗。 */
function openNewFund(): void {
  editingFlow.value = null
  fundDialogVisible.value = true
}

/** 打开礼物新建弹窗。 */
function openNewGift(): void {
  editingGift.value = null
  giftDialogVisible.value = true
}

/** 归一记录只带精简字段，详情需完整记录：按 id 拉一次再喂给表单。 */
async function openRecordDetail(payload: {
  source: TimelineSource
  record: TimelineRecord
}): Promise<void> {
  try {
    if (payload.source === 'activity') {
      editingActivity.value = await activitiesApi.get(payload.record.id)
      activityDialogVisible.value = true
    } else if (payload.source === 'gift') {
      editingGift.value = await giftsApi.get(payload.record.id)
      giftDialogVisible.value = true
    } else {
      editingFlow.value = await fundsApi.get(payload.record.id)
      fundDialogVisible.value = true
    }
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '打开失败')
  }
}

/** 保存后刷新「该记录所属」的 Tab 并切过去。
 *
 * 不能用当前激活的 Tab：Tab 标签上的「记一笔」带 @click.stop，点它不会切换 Tab，
 * 于是在别的 Tab 处于激活态时新建，保存后刷新的会是那个无关的 Tab。
 */
async function refreshTab(source: TimelineSource): Promise<void> {
  activeTab.value = source
  await timelineRefs.value[source]?.reload()
}

// ---- 关系区块状态 ----
const relations = ref<RelationshipOut[]>([])
const relationTypes = ref<RelationshipTypeOut[]>([])
const contactOptions = ref<{ label: string; value: number }[]>([])
const showRelationForm = ref(false)
const relationSubmitting = ref(false)
const relationDraft = ref<{
  other_id: number | null
  type_id: number | null
  from_role: string | null
  to_role: string | null
}>({
  other_id: null,
  type_id: null,
  from_role: null,
  to_role: null,
})

/** 关系类型的分组下拉选项（家人/朋友/工作/其他 分组，供 el-option-group 渲染）。 */
const typeOptions = computed(() => {
  const groupLabel: Record<string, string> = {
    family: '家人',
    friend: '朋友',
    work: '工作',
    romance: '情感',
    other: '其他',
  }
  const groups = new Map<string, { label: string; value: number }[]>()
  for (const relationType of relationTypes.value) {
    const list = groups.get(relationType.group_name) ?? []
    list.push({ label: relationType.name, value: relationType.id })
    groups.set(relationType.group_name, list)
  }
  return [...groups.entries()].map(([group, children]) => ({
    label: groupLabel[group] ?? group,
    key: group,
    children,
  }))
})

/** 当前选中的关系类型（系统类型联动角色下拉，D15）。 */
const selectedRelationType = computed(() =>
  relationTypes.value.find((item) => item.id === relationDraft.value.type_id) ?? null,
)
const fromRoleChoices = computed(() =>
  selectedRelationType.value?.kind ? ROLE_DOMAINS[selectedRelationType.value.kind].from : [],
)
const toRoleChoices = computed(() =>
  selectedRelationType.value?.kind ? ROLE_DOMAINS[selectedRelationType.value.kind].to : [],
)

/** 关系文案：称谓优先（D15 kinship_label，如"爸爸/舅舅"），缺省退回「我是对方的…」句式。 */
function relationSentence(relation: RelationshipOut): string {
  const me = contact.value?.display_name ?? ''
  if (relation.kinship_label) {
    return `${relation.other_contact_name} 是 ${me} 的 ${relation.kinship_label}`
  }
  return `${me} 是 ${relation.other_contact_name} 的 ${relation.type_label}`
}

async function loadRelations(): Promise<void> {
  if (!contact.value) return
  try {
    const [relationshipList, relationshipTypes, contacts] = await Promise.all([
      graphApi.relationships(contact.value.id),
      graphApi.relationshipTypes(),
      contactsApi.list(),
    ])
    relations.value = relationshipList
    relationTypes.value = relationshipTypes
    contactOptions.value = contacts
      .filter((item) => item.id !== contact.value?.id)
      .map((item) => ({ label: item.display_name, value: item.id }))
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('关系加载失败')
  }
}

/** 提交建立关系（两端可读校验在服务端；重复边提示已存在）。 */
async function submitRelation(): Promise<void> {
  if (!contact.value || !relationDraft.value.other_id || !relationDraft.value.type_id) return
  relationSubmitting.value = true
  try {
    await graphApi.createRelationship({
      from_contact_id: contact.value.id,
      to_contact_id: relationDraft.value.other_id,
      type_id: relationDraft.value.type_id,
      from_role: relationDraft.value.from_role,
      to_role: relationDraft.value.to_role,
    })
    ElMessage.success('关系已建立')
    relationDraft.value = { other_id: null, type_id: null, from_role: null, to_role: null }
    showRelationForm.value = false
    await loadRelations()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '建立关系失败')
  } finally {
    relationSubmitting.value = false
  }
}

/** 删除关系边（仅所有者显示该操作，服务端兜底校验）。 */
async function removeRelation(relation: RelationshipOut): Promise<void> {
  try {
    await graphApi.removeRelationship(relation.id)
    ElMessage.success('已删除')
    await loadRelations()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '删除失败')
  }
}

/** 农历日期的展示格式已由 lunarLabel 统一处理。 */

async function loadContact(): Promise<void> {
  loading.value = true
  try {
    contact.value = await contactsApi.get(contactId.value)
    await loadRelations()
    // el-table 由 v-if+异步数据挂载时容器宽为 0，列宽 fit 计算会崩（表体出现超宽列），
    // 数据与 DOM 就位后强制重排一次
    await nextTick()
    dateTableRef.value?.doLayout()
    relationTableRef.value?.doLayout()
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      ElMessage.error('联系人不存在或不可见')
      router.replace({ name: 'contacts' })
      return
    }
    if (!(error instanceof ApiError && error.status === 401)) {
      ElMessage.error('详情加载失败')
    }
  } finally {
    loading.value = false
  }
}

async function toggleVisibility(value: 'private' | 'family'): Promise<void> {
  if (!contact.value) return
  saving.value = true
  try {
    contact.value = await contactsApi.update(contact.value.id, { visibility: value })
  } catch (error) {
    const text = error instanceof ApiError ? error.message : '保存失败'
    ElMessage.error(text)
  } finally {
    saving.value = false
  }
}

async function promoteEdge(): Promise<void> {
  if (!contact.value) return
  try {
    contact.value = await contactsApi.promote(contact.value.id)
    ElMessage.success('已升级为直接联系人')
  } catch (error) {
    const text = error instanceof ApiError ? error.message : '升级失败'
    ElMessage.error(text)
  }
}

async function archiveContact(): Promise<void> {
  if (!contact.value) return
  try {
    await contactsApi.archive(contact.value.id)
    ElMessage.success('已归档')
    router.replace({ name: 'contacts' })
  } catch (error) {
    const text = error instanceof ApiError ? error.message : '归档失败'
    ElMessage.error(text)
  }
}

onMounted(loadContact)

watch(contactId, () => {
  if (!Number.isNaN(contactId.value)) void loadContact()
})

</script>

<template>
  <div class="crm-page">
    <!-- naive 的 text-color="#787774" 等值于 tokens.color.muted，改用 token 内联生效 -->
    <el-button
      text
      class="back"
      :style="{ color: tokens.color.muted }"
      @click="router.push({ name: 'contacts' })"
    >
      ← 返回名册
    </el-button>

    <template v-if="contact">
      <header class="head">
        <ContactAvatar :name="contact.display_name" :size="64" />
        <div class="head-main">
          <div class="head-name-row">
            <h1 class="head-name crm-display">{{ contact.display_name }}</h1>
            <!-- naive 的 :color 对象改用 el-tag 的 CSS 变量注入，色值仍取自 tokens -->
            <el-tag
              v-if="contact.tier === 'edge'"
              size="small"
              :style="{
                '--el-tag-bg-color': tokens.color.bone,
                '--el-tag-text-color': tokens.color.muted,
                '--el-tag-border-color': 'transparent',
              }"
            >
              边缘联系人
            </el-tag>
            <el-tag
              v-if="contact.visibility === 'private'"
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
          <p class="head-meta">{{ contact.owner_display_name }} 记录于 {{ contact.created_at.slice(0, 10) }}</p>
        </div>
        <div v-if="isOwned" class="head-actions">
          <el-button @click="openEdit">编辑资料</el-button>
          <el-button v-if="contact.tier === 'edge'" @click="promoteEdge">升级为直接联系人</el-button>
          <el-button type="danger" plain @click="archiveContact">归档</el-button>
        </div>
      </header>

        <section class="block">
          <h2 class="block-title">基本信息</h2>
          <el-descriptions :column="2" class="info-desc" label-class-name="info-label-cell">
            <el-descriptions-item label="姓名">{{ contact.name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="性别">{{ genderLabel[contact.gender] ?? '未知' }}</el-descriptions-item>
            <el-descriptions-item label="单位">{{ contact.organization || '—' }}</el-descriptions-item>
            <el-descriptions-item label="所在地">
              {{ contact.location || '—' }}
              <!-- 坐标解析状态提示（D14）：none=已尝试未命中，其余展示来源 -->
              <span v-if="contact.location_source === 'none'" class="geo-miss">坐标未解析</span>
            </el-descriptions-item>
            <el-descriptions-item label="备注">{{ contact.bio || '—' }}</el-descriptions-item>
            <el-descriptions-item label="家人可见">
              <!-- 受控用法对应 EP 的 :model-value + @update:model-value -->
              <el-switch
                v-if="isOwned"
                :model-value="contact.visibility"
                :disabled="saving"
                active-value="family"
                inactive-value="private"
                @update:model-value="(v: 'private' | 'family') => toggleVisibility(v)"
              />
              <span v-else>{{ contact.visibility === 'family' ? '家庭可见' : '私密' }}</span>
            </el-descriptions-item>
          </el-descriptions>
        </section>

        <section class="block">
          <div class="block-head">
            <h2 class="block-title">重要日期</h2>
            <el-button v-if="isOwned" text @click="openDateCreate">添加日期</el-button>
          </div>

          <!-- 日期 / 提醒 / 操作 三列；操作列仅所有者渲染 -->
          <el-table v-if="contact.dates.length" ref="dateTableRef" :data="contact.dates" row-key="id" class="date-table">
            <el-table-column label="日期" min-width="240">
              <template #default="{ row }">{{ dateLine(row) }}</template>
            </el-table-column>
            <el-table-column label="提醒" min-width="150">
              <template #default="{ row }">
                <span class="date-remind">提前 {{ row.reminder_lead_days.join('、') }} 天提醒</span>
              </template>
            </el-table-column>
            <el-table-column v-if="isOwned" label="操作" width="130" align="right">
              <template #default="{ row }">
                <el-button text @click="openDateEdit(row)">编辑</el-button>
                <!-- 问题文本须走 el-popconfirm 的 title 属性（默认插槽不会被渲染）；stop 防触发行级交互 -->
                <el-popconfirm title="删除这条日期？" @confirm="removeDate(row)">
                  <template #reference>
                    <el-button text type="danger" @click.stop>删除</el-button>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
          <p v-else class="block-empty">还没有记录重要日期</p>
        </section>

      <section class="block">
        <div class="block-head">
          <h2 class="block-title">关 系</h2>
          <el-button text @click="showRelationForm = true">建立关系</el-button>
        </div>

        <!-- 关系句 / 记录人 / 操作 三列；删除仅本条记录人可见 -->
        <el-table v-if="relations.length" ref="relationTableRef" :data="relations" row-key="id" class="relation-table">
          <el-table-column label="关系" min-width="260">
            <template #default="{ row }">{{ relationSentence(row) }}</template>
          </el-table-column>
          <el-table-column label="记录人" min-width="110">
            <template #default="{ row }">
              <span class="relation-owner">{{ row.owner_display_name }} 记录</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="110" align="right" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.owner_user_id === auth.user?.id"
                text
                type="danger"
                @click="removeRelation(row)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <p v-else class="relation-empty">还没有记录关系，试试从右侧建立一条</p>
      </section>

      <section class="block">
        <div class="block-head">
          <h2 class="block-title">往 来</h2>
          <span class="block-hint">活动 · 资金 · 礼物，各按时间倒序</span>
        </div>
        <el-tabs v-model="activeTab">
          <el-tab-pane name="activity">
            <template #label>
              <span class="tab-label">
                活动
                <el-button text size="small" @click.stop="openNewActivity">记一笔</el-button>
              </span>
            </template>
            <RecordTimeline
              :ref="(el) => (timelineRefs.activity = el as never)"
              source="activity"
              :contact-id="contactId"
              @open-detail="openRecordDetail"
            />
          </el-tab-pane>
          <el-tab-pane name="fund">
            <template #label>
              <span class="tab-label">
                资金往来
                <el-button text size="small" @click.stop="openNewFund">记一笔</el-button>
              </span>
            </template>
            <RecordTimeline
              :ref="(el) => (timelineRefs.fund = el as never)"
              source="fund"
              :contact-id="contactId"
              @open-detail="openRecordDetail"
            />
          </el-tab-pane>
          <el-tab-pane name="gift">
            <template #label>
              <span class="tab-label">
                礼物往来
                <el-button text size="small" @click.stop="openNewGift">记一笔</el-button>
              </span>
            </template>
            <RecordTimeline
              :ref="(el) => (timelineRefs.gift = el as never)"
              source="gift"
              :contact-id="contactId"
              @open-detail="openRecordDetail"
            />
          </el-tab-pane>
        </el-tabs>
      </section>

      <ActivityFormDialog
        v-model:visible="activityDialogVisible"
        :activity="editingActivity"
        :preset-contact-id="contactId"
        @saved="refreshTab('activity')"
      />
      <GiftFormDialog
        v-model:visible="giftDialogVisible"
        :gift="editingGift"
        :preset-contact-id="contactId"
        @saved="refreshTab('gift')"
      />
      <FundFormDialog
        v-model:visible="fundDialogVisible"
        :flow="editingFlow"
        :preset-contact-id="contactId"
        @saved="refreshTab('fund')"
      />

      <!-- 编辑资料：官方 el-dialog + el-form（D16 组件化） -->
      <el-dialog v-model="showEditDialog" title="编辑资料" width="480px" destroy-on-close>
        <el-form label-position="top">
          <el-form-item label="姓名">
            <el-input v-model="editDraft.name" placeholder="姓名" />
          </el-form-item>
          <div class="form-two-col">
            <el-form-item label="昵称">
              <el-input v-model="editDraft.nickname" placeholder="怎么称呼（选填）" />
            </el-form-item>
            <el-form-item label="性别">
              <el-select v-model="editDraft.gender">
                <el-option v-for="opt in genderOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item label="单位">
            <el-input v-model="editDraft.organization" placeholder="选填" />
          </el-form-item>
          <el-form-item label="所在地">
            <el-input v-model="editDraft.location" placeholder="如：上海市浦东新区（保存时自动解析坐标）" />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="editDraft.bio" type="textarea" :rows="2" placeholder="一句话简介（选填）" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showEditDialog = false">取消</el-button>
          <el-button type="primary" :loading="editSaving" @click="submitEdit">保存</el-button>
        </template>
      </el-dialog>

      <!-- 重要日期：新增/编辑共用一个弹窗 -->
      <el-dialog
        v-model="showDateForm"
        :title="editingDateId === null ? '添加重要日期' : '编辑重要日期'"
        width="440px"
        destroy-on-close
      ><el-form label-position="top">
            <div class="date-form-row">
              <el-select v-model="dateDraft.type" class="date-type-select">
                <el-option v-for="opt in dateTypeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
              <el-select v-model="dateDraft.calendar" class="date-cal-select">
                <el-option v-for="opt in calendarOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </div>
            <div v-if="dateDraft.calendar === 'solar'" class="date-form-row">
              <!-- 原值为毫秒时间戳（非字符串日期），故按 EP 默认绑定 Date 对象，不加 value-format -->
              <el-date-picker
                v-model="dateDraft.solar_ts"
                type="date"
                class="full-width"
                placeholder="选择公历日期"
              />
            </div>
            <div v-else class="date-form-row">
              <el-select v-model="dateDraft.lunar_month" class="lunar-select">
                <el-option v-for="opt in lunarMonthOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
              <el-select v-model="dateDraft.lunar_day" class="lunar-select">
                <el-option v-for="opt in lunarDayOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
              <label class="leap-toggle">
                <el-switch v-model="dateDraft.lunar_is_leap" size="small" />
                <span>闰月</span>
              </label>
            </div>
            <el-form-item label="提前提醒">
              <el-select v-model="dateDraft.leads" multiple class="full-width">
                <el-option v-for="opt in leadOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </el-form-item>
          </el-form>
        <template #footer>
          <el-button @click="showDateForm = false">取消</el-button>
          <el-button
            type="primary"
            :loading="dateSaving"
            :disabled="dateDraft.calendar === 'solar' && !dateDraft.solar_ts"
            @click="submitDate"
          >
            保存
          </el-button>
        </template>
      </el-dialog>

      <!-- 建立关系 -->
      <el-dialog v-model="showRelationForm" title="建立关系" width="440px" destroy-on-close>
        <el-form label-position="top">
          <el-form-item label="关系类型">
            <el-select v-model="relationDraft.type_id" filterable placeholder="选关系（如 丈夫）" class="full-w">
              <el-option-group v-for="group in typeOptions" :key="group.key" :label="group.label">
                <el-option v-for="opt in group.children" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-option-group>
            </el-select>
          </el-form-item>
          <div class="form-two-col">
            <el-form-item label="我是对方的…">
              <el-select v-model="relationDraft.from_role" placeholder="角色" class="full-w">
                <el-option
                  v-for="role in fromRoleChoices"
                  :key="role"
                  :label="ROLE_LABELS[role] ?? role"
                  :value="role"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="对方是我的…">
              <el-select v-model="relationDraft.to_role" placeholder="角色" class="full-w">
                <el-option
                  v-for="role in toRoleChoices"
                  :key="role"
                  :label="ROLE_LABELS[role] ?? role"
                  :value="role"
                />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item label="对方">
            <el-select v-model="relationDraft.other_id" filterable placeholder="选对方" class="full-w">
              <el-option v-for="opt in contactOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showRelationForm = false">取消</el-button>
          <el-button
            type="primary"
            :loading="relationSubmitting"
            :disabled="!relationDraft.other_id || !relationDraft.type_id"
            @click="submitRelation"
          >
            建立
          </el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<style scoped>
.geo-miss {
  color: var(--crm-muted);
  font-size: 12px;
  margin-left: 6px;
}
.back {
  margin-bottom: 18px;
  padding-left: 0;
}
.head {
  display: flex;
  align-items: center;
  gap: 18px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--crm-line);
}
.head-main {
  flex: 1;
  min-width: 0;
}
.head-name-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.head-name {
  margin: 0;
  font-size: 28px;
}
.head-meta {
  margin: 8px 0 0;
  color: var(--crm-muted);
  font-size: 13px;
}
.head-actions {
  display: flex;
  gap: 10px;
}
.block {
  margin-top: 32px;
}
.block-title {
  margin: 0 0 14px;
  font-size: 16px;
  font-weight: 600;
}
.info-row:last-child {
  border-bottom: none;
}
.date-table {
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
  min-width: 0;
}
.date-remind {
  color: var(--crm-muted);
  font-size: 13px;
}
.date-form-row {
  display: flex;
  gap: 10px;
  align-items: center;
}
.date-type-select,
.date-cal-select {
  width: 140px;
}
.lunar-select {
  width: 120px;
}
.leap-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--crm-muted);
  font-size: 13px;
}
.lead-row {
  justify-content: flex-start;
}
.lead-label {
  color: var(--crm-muted);
  font-size: 13px;
  flex-shrink: 0;
}
.lead-select {
  flex: 1;
}
.full-width {
  width: 100%;
}
.date-form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.block-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.relation-other {
  flex: 1;
}
.relation-table {
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
  min-width: 0;
}
.relation-owner {
  color: var(--crm-muted);
  font-size: 13px;
}
.relation-empty {
  color: var(--crm-muted);
  font-size: 14px;
}
.block-empty {
  color: var(--crm-muted);
  font-size: 14px;
}
.block-hint {
  color: var(--crm-muted);
  font-size: 13px;
}
.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
</style>
