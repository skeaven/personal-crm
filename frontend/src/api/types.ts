/** 后端 API 契约类型（与 backend schemas.py 对应；openapi-typescript 生成链路后续接入） */

export interface UserOut {
  id: number
  username: string
  display_name: string
  family_id: number
  /** "我"绑定的联系人（D15 视角推导起点；null=未绑定） */
  contact_id: number | null
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: UserOut
}

/** 个人访问令牌条目（只有元信息，绝不含明文与哈希） */
export interface TokenOut {
  id: number
  name: string
  created_at: string
  last_used_at: string | null
}

/** 签发响应：明文 token 只在这一个响应里出现 */
export interface TokenIssueOut extends TokenOut {
  token: string
}

/** 签发个人令牌的请求 */
export interface TokenIssueIn {
  name: string
}

export interface DuplicateWarning {
  contact_id: number
  display_name: string
  owner_display_name: string
  tier: 'direct' | 'edge'
}

export interface ContactOut {
  id: number
  tier: 'direct' | 'edge'
  name: string
  nickname: string | null
  display_name: string
  gender: 'male' | 'female' | 'other' | 'unknown'
  organization: string | null
  phone: string | null
  qq: string | null
  wechat: string | null
  email: string | null
  current_address: string | null
  family_address: string | null
  hobbies: string | null
  school_name: string | null
  location: string | null
  location_lng: number | null
  location_lat: number | null
  location_source: string | null
  location_province: string | null
  bio: string | null
  visibility: 'private' | 'family'
  status: 'active' | 'archived'
  owner_user_id: number
  owner_display_name: string
  created_at: string
  updated_at: string
}

export interface ContactCreate {
  tier: 'direct' | 'edge'
  name?: string
  nickname?: string | null
  gender?: 'male' | 'female' | 'other' | 'unknown'
  organization?: string | null
  phone?: string | null
  qq?: string | null
  wechat?: string | null
  email?: string | null
  current_address?: string | null
  family_address?: string | null
  hobbies?: string | null
  school_name?: string | null
  bio?: string | null
  visibility?: 'private' | 'family'
  confirm_duplicate?: boolean
  location?: string
}

export interface ContactUpdate {
  name?: string
  nickname?: string | null
  gender?: 'male' | 'female' | 'other' | 'unknown'
  organization?: string | null
  phone?: string | null
  qq?: string | null
  wechat?: string | null
  email?: string | null
  current_address?: string | null
  family_address?: string | null
  hobbies?: string | null
  school_name?: string | null
  location?: string | null
  bio?: string | null
  visibility?: 'private' | 'family'
}

export interface ContactCreateResponse {
  created: boolean
  contact: ContactOut | null
  duplicate_warnings: DuplicateWarning[]
}

export interface ImportantDateOut {
  id: number
  type: 'birthday' | 'anniversary' | 'memorial' | 'other'
  title: string | null
  calendar: 'solar' | 'lunar'
  date_solar: string | null
  lunar_month: number | null
  lunar_day: number | null
  lunar_is_leap: boolean
  yearly: boolean
  reminder_lead_days: number[]
}

export interface ImportantDateCreate {
  type?: 'birthday' | 'anniversary' | 'memorial' | 'other'
  title?: string | null
  calendar: 'solar' | 'lunar'
  date_solar?: string | null
  lunar_month?: number | null
  lunar_day?: number | null
  lunar_is_leap?: boolean
  yearly?: boolean
  reminder_lead_days?: number[]
}

export interface ImportantDateUpdate {
  type?: 'birthday' | 'anniversary' | 'memorial' | 'other'
  title?: string | null
  calendar?: 'solar' | 'lunar'
  date_solar?: string | null
  lunar_month?: number | null
  lunar_day?: number | null
  lunar_is_leap?: boolean
  yearly?: boolean
  reminder_lead_days?: number[]
}

/** 详情页契约：联系人全量 + 关联区块（时间线/礼物/资金等后续增量挂载） */
export interface ContactDetailOut extends ContactOut {
  dates: ImportantDateOut[]
}

// ---------- dashboard 模块：待办聚合 ----------

export type TodoSource = 'task' | 'wish' | 'repayment' | 'activity' | 'birthday'
export type TodoBucket = 'todo' | 'overdue' | 'done' | 'all'

/** 主页统计卡（口径与名册 ?activity= 过滤联动）。 */
export interface DashboardStatsOut {
  total_contacts: number
  recent_contacted: number
  stale_half_year: number
  open_tasks: number
}

export interface TodoItemOut {
  source: TodoSource
  ref_id: number
  title: string
  contact_id: number | null
  contact_name: string | null
  due_date: string | null
  days_left: number | null
  lunar_label: string | null
  bucket: TodoBucket
}

// ---------- graph 模块：关系类型 / 关系边 / 图数据 ----------

export type RelationGroup = 'family' | 'friend' | 'work' | 'romance' | 'other'

export interface RelationshipTypeOut {
  id: number
  group_name: RelationGroup
  name: string
  reverse_name: string | null
  is_system: boolean
  kind: 'parent' | 'spouse' | 'sibling' | null
}

/** 系统类型角色的中文标签（表单下拉与展示共用，D15）。 */
export const ROLE_LABELS: Record<string, string> = {
  father: '父亲', mother: '母亲', son: '儿子', daughter: '女儿',
  husband: '丈夫', wife: '妻子', partner: '伴侣',
  elder_brother: '哥哥', younger_brother: '弟弟',
  elder_sister: '姐姐', younger_sister: '妹妹',
}

/** 按 kind 的角色值域（与后端 kinship.ROLE_DOMAINS 对齐）。 */
export const ROLE_DOMAINS: Record<string, { from: string[]; to: string[] }> = {
  parent: { from: ['father', 'mother'], to: ['son', 'daughter'] },
  spouse: { from: ['husband', 'wife', 'partner'], to: ['husband', 'wife', 'partner'] },
  sibling: {
    from: ['elder_brother', 'younger_brother', 'elder_sister', 'younger_sister'],
    to: ['elder_brother', 'younger_brother', 'elder_sister', 'younger_sister'],
  },
}

export interface RelationshipTypeCreate {
  group_name: RelationGroup
  name: string
  reverse_name?: string | null
}

export interface RelationshipCreate {
  from_contact_id: number
  to_contact_id: number
  type_id: number
  from_role?: string | null
  to_role?: string | null
  status?: 'active' | 'former'
  note?: string | null
}

export interface RelationshipOut {
  id: number
  direction: 'out' | 'in'
  other_contact_id: number
  other_contact_name: string
  other_tier: 'direct' | 'edge'
  type_id: number
  type_label: string
  type_name: string
  kind: 'parent' | 'spouse' | 'sibling' | null
  kinship_label: string | null
  status: 'active' | 'former'
  note: string | null
  owner_user_id: number
  owner_display_name: string
  created_at: string
}

export interface GraphNodeOut {
  id: number
  name: string
  tier: 'direct' | 'edge'
}

export interface GraphLinkOut {
  id: number
  source: number
  target: number
  label: string
}

export interface KinshipStepOut {
  contact_id: number
  name: string
  kind: string | null
  role: string | null
}

export interface KinshipOut {
  found: boolean
  title: string | null
  generation_diff: number | null
  path: KinshipStepOut[]
}

// ---------- reminders 模块：主动提醒（D22） ----------

export interface ReminderOut {
  id: number
  source: 'date' | 'task' | 'repayment'
  ref_id: number
  due_date: string
  days_left: number
  title: string
  contact_id: number | null
  read_at: string | null
  created_at: string
}

export interface ReminderScanOut {
  created: number
  refreshed: number
  removed: number
  sources: Record<string, number>
}

// ---------- contacts 模块：地图数据（D14） ----------

export interface MapPointOut {
  contact_id: number
  display_name: string
  tier: 'direct' | 'edge'
  lng: number
  lat: number
}

export interface ProvinceCountOut {
  name: string
  count: number
}

export interface MapPointsOut {
  points: MapPointOut[]
  provinces: ProvinceCountOut[]
}

export interface GraphDataOut {
  nodes: GraphNodeOut[]
  links: GraphLinkOut[]
}

// ---------- dashboard 模块：联系人时间线 ----------

export type TimelineSource = 'gift' | 'fund' | 'activity'

export interface TimelineItemOut {
  /** note 是 dashboard 聚合时间线新接入的来源，往来 Tab 的分页组件不消费它 */
  source: TimelineSource | 'note'
  ref_id: number
  occurred_at: string
  title: string
  summary: string | null
  amount: string | null
  direction: string | null
  extra_label: string | null
}

export interface TimelineOut {
  contact_id: number
  items: TimelineItemOut[]
}

// ---------- ai 模块：对话 / 工具 / 写入提议 ----------

export interface ToolOut {
  name: string
  label: string
  description: string
  risk: 'read' | 'write_queue'
}

export interface PendingActionOut {
  id: number
  tool_name: string
  payload: Record<string, unknown>
  status: 'pending' | 'approved' | 'rejected' | 'executed'
  result: { ok: boolean; message?: string; error?: string } | null
  created_at: string
}

export interface AiLlmConfigIn {
  base_url: string
  api_key: string
  model: string
  temperature?: number
}

export interface AiLlmConfigOut {
  configured: boolean
  base_url?: string
  model?: string
  api_key_masked?: string
  temperature?: number
}

export interface AiTestOut {
  ok: boolean
  message: string
}

export interface AiEmbeddingConfigIn {
  base_url: string
  api_key: string
  model: string
}

export interface AiEmbeddingConfigOut {
  configured: boolean
  base_url?: string
  model?: string
  api_key_masked?: string
}

export interface RebuildOut {
  embedded: number
  skipped: number
  removed: number
}

/** 语义搜索结果条目（按 cosine 距离升序） */
export interface SearchItemOut {
  entity_type: string
  entity_id: number
  content: string
  distance: number
}

/** AI 会话索引（列表展示用） */
export interface AiSessionOut {
  session_id: string
  title: string
  created_at: string
  updated_at: string
}

/** 历史消息：与流式渲染同形状，前端复用同一套渲染 */
export interface HistoryMessageOut {
  role: 'user' | 'assistant'
  content: string
  tools: string[]
}

// ---------- records 模块：活动 / 任务 ----------

export interface ActivityOut {
  id: number
  title: string
  occurred_at: string | null
  location: string | null
  detail: string | null
  owner_user_id: number
  owner_display_name: string
  visibility: 'private' | 'family'
  created_at: string
  updated_at: string
  participant_ids: number[]
  images: ActivityImageOut[]
}

/** 活动图片（响应）：前端拿 id 拼鉴权读取地址 */
export interface ActivityImageOut {
  id: number
  sort_order: number
}

/** 图片提交项：保留已有图给 id，新增图给 temp_path；数组顺序即展示顺序 */
export interface ImageRefIn {
  id?: number
  temp_path?: string
}

/** 联系人往来的归一记录：三源（活动/资金/礼物）在时间线里统一按这个形状渲染 */
export interface TimelineRecord {
  id: number
  occurredAt: string | null
  title: string
  summary: string | null
  amount: string | null
  direction: string | null
  extraLabel: string | null
  ownerUserId: number
  /** 活动封面图 id（资金/礼物没有图片，恒为 null） */
  coverImageId: number | null
}

/** 分页列表契约：items 为响应体，total 来自 X-Total-Count 响应头 */
export interface Paged<T> {
  items: T[]
  total: number
}

export interface ActivityCreate {
  title: string
  occurred_at?: string | null
  location?: string | null
  detail?: string | null
  participant_ids?: number[]
  images?: ImageRefIn[]
}

export interface ActivityUpdate {
  title?: string
  occurred_at?: string | null
  location?: string | null
  detail?: string | null
  participant_ids?: number[]
  images?: ImageRefIn[]
}

export type TaskStatus = 'todo' | 'done' | 'cancelled'

export interface TaskOut {
  id: number
  title: string
  contact_id: number | null
  detail: string | null
  due_at: string | null
  status: TaskStatus
  completed_at: string | null
  owner_user_id: number
  owner_display_name: string
  visibility: 'private' | 'family'
  created_at: string
  updated_at: string
}

export interface TaskCreate {
  title: string
  contact_id?: number | null
  detail?: string | null
  due_at?: string | null
}

export interface TaskUpdate {
  title?: string
  contact_id?: number | null
  detail?: string | null
  due_at?: string | null
  status?: TaskStatus
}

// ---------- records 模块：备注 ----------

export interface NoteOut {
  id: number
  contact_id: number | null
  content: string
  owner_user_id: number
  owner_display_name: string
  visibility: 'private' | 'family'
  created_at: string
  updated_at: string
}

export interface NoteCreate {
  contact_id: number
  content: string
}

export interface NoteUpdate {
  content: string
}

// ---------- gifts 模块：礼物往来 / 愿望清单 ----------

export type GiftDirection = 'given' | 'received'

export interface GiftOut {
  id: number
  contact_id: number | null
  direction: GiftDirection
  title: string
  occasion: string | null
  amount: string | null
  currency: string
  given_at: string | null
  link: string | null
  description: string | null
  owner_user_id: number
  owner_display_name: string
  visibility: 'private' | 'family'
  created_at: string
  updated_at: string
}

export interface GiftCreate {
  contact_id?: number | null
  direction: GiftDirection
  title: string
  occasion?: string | null
  amount?: string | null
  currency?: string
  given_at?: string | null
  link?: string | null
  description?: string | null
}

export interface GiftUpdate {
  contact_id?: number | null
  direction?: GiftDirection
  title?: string
  occasion?: string | null
  amount?: string | null
  currency?: string
  given_at?: string | null
  link?: string | null
  description?: string | null
}

export type WishlistStatus = 'open' | 'purchased' | 'given'

export interface WishlistOut {
  id: number
  contact_id: number | null
  title: string
  amount: string | null
  currency: string
  link: string | null
  description: string | null
  status: WishlistStatus
  target_date: string | null
  converted_gift_id: number | null
  owner_user_id: number
  owner_display_name: string
  visibility: 'private' | 'family'
  created_at: string
  updated_at: string
}

export interface WishlistCreate {
  contact_id?: number | null
  title: string
  amount?: string | null
  currency?: string
  link?: string | null
  description?: string | null
  status?: WishlistStatus
  target_date?: string | null
}

export interface WishlistUpdate {
  contact_id?: number | null
  title?: string
  amount?: string | null
  currency?: string
  link?: string | null
  description?: string | null
  status?: WishlistStatus
  target_date?: string | null
}

export interface WishlistConvertOut {
  gift: GiftOut
  item: WishlistOut
}

// ---------- funds 模块：资金往来 ----------

export type FundDirection = 'out' | 'in'
export type FundCategory = 'loan' | 'repayment' | 'gift_money' | 'other'
export type FundStatus = 'pending' | 'settled'

export interface FundFlowOut {
  id: number
  contact_id: number | null
  direction: FundDirection
  category: FundCategory
  amount: string
  currency: string
  occurred_at: string
  due_at: string | null
  status: FundStatus | null
  settled_at: string | null
  description: string | null
  owner_user_id: number
  owner_display_name: string
  visibility: 'private' | 'family'
  created_at: string
  updated_at: string
}

export interface FundFlowCreate {
  contact_id?: number | null
  direction: FundDirection
  category: FundCategory
  amount: string
  currency?: string
  occurred_at: string
  due_at?: string | null
  description?: string | null
}

export interface FundFlowUpdate {
  contact_id?: number | null
  direction?: FundDirection
  category?: FundCategory
  amount?: string
  currency?: string
  occurred_at?: string
  due_at?: string | null
  status?: FundStatus
  description?: string | null
}
