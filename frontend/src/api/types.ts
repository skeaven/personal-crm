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

export interface DuplicateWarning {
  contact_id: number
  display_name: string
  owner_display_name: string
  tier: 'direct' | 'edge'
}

export interface ContactOut {
  id: number
  tier: 'direct' | 'edge'
  last_name: string
  first_name: string
  nickname: string | null
  display_name_override: string | null
  display_name: string
  gender: 'male' | 'female' | 'other' | 'unknown'
  organization: string | null
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
  last_name?: string
  first_name?: string
  nickname?: string | null
  display_name_override?: string | null
  gender?: 'male' | 'female' | 'other' | 'unknown'
  organization?: string | null
  bio?: string | null
  visibility?: 'private' | 'family'
  confirm_duplicate?: boolean
  location?: string
}

export interface ContactUpdate {
  last_name?: string
  first_name?: string
  nickname?: string | null
  gender?: 'male' | 'female' | 'other' | 'unknown'
  organization?: string | null
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
  source: TimelineSource
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
}

export interface ActivityCreate {
  title: string
  occurred_at?: string | null
  location?: string | null
  detail?: string | null
  participant_ids?: number[]
}

export interface ActivityUpdate {
  title?: string
  occurred_at?: string | null
  location?: string | null
  detail?: string | null
  participant_ids?: number[]
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
