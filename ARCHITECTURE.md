# 模块架构：原子模块清单与依赖关系

> 文档目的：在写代码之前，把整个系统的原子模块、各自拥有的数据表、对外接口与依赖方向一次性理清，作为**结构事实源**。新增或调整模块，必须先改本文档登记，再动代码。
>
> 上游依据：`PROJECT_BACKGROUND.md`（需求 R1–R6）、`TECH_DECISIONS.md`（D1–D12）、`DATA_MODEL.md`（字段级表结构）。
> 创建：2026-09-21。

---

## 1. 原子模块清单

划分原则：**一个模块 = 一组高内聚的数据表 + 围绕它们的业务规则**，写权独占；聚合与 AI 是纯消费方，不拥有业务表。

| 层 | 模块 | 位置 | 拥有的表 | 职责与边界 | Level |
|---|---|---|---|---|---|
| L0 地基 | core | `app/core/` | — | 配置、引擎/会话、错误类型、密码/JWT；mixins（D7 三件套载体） | ✅ |
| L0 横切 | permission | `app/services/permission.py` | — | 全系统唯一判权点（D7/D11 红线），REST/MCP/内部 agent 共用 | ✅ |
| L0 横切 | storage | `app/services/storage.py` | — | **文件存储唯一实现点**（临时区/正式区/缩略图/路径安全，D18）；配置注入、无表无状态；文件删除经 `defer_delete` 延到事务提交后 | ✅ |
| L0 横切 | uploads | `app/modules/uploads/` | — | 通用临时上传与本人读取端点（无表）；业务图片的鉴权读取归各业务模块 | ✅ |
| L1 身份 | auth | `app/modules/auth/` | families, users, user_tokens | 注册登录、JWT、家庭组成员、MCP 个人访问令牌 | ✅ |
| L2 人 | contacts | `app/modules/contacts/` | contacts, important_dates | 名册 CRUD、direct/edge 双层与升级、展示名规则、同名检测、重要日期；**历法引擎 `calendar.py`（纯函数：农历↔公历、下次发生日）随本模块**；**"最近联系时间"口径（只读 join activities）随本模块**；**位置字段**（location 文本 + 坐标缓存列，保存时经 geo 解析，D14） | ✅ |
| L2 地理 | geo | `app/modules/geo/` | **无表**（坐标缓存列在 contacts） | **纯函数模块**：地理编码 provider（高德 geo + 静态市县区坐标表 `cities.json` 降级，D14）；配置（key）由调用方注入，自身不读表不发状态，可独立测试；地图页数据端点在 contacts 聚合，不经 geo | ✅ |
| L3 连接 | graph | `app/modules/graph/` | relationship_types, relationships | 关系类型字典（系统结构化类型 parent/spouse/sibling + 自定义，D15）、关系边 CRUD（**角色化：from_role/to_role/status**，跨用户边、可见性取交集）、图数据组装、**视角推导与称谓引擎 `kinship.py`（纯函数：角色路径→中文称呼+辈分）**；users.contact_id 绑定"我是谁"后以账号为起点推导 | L2 |
| L3 记录 | records | `app/modules/records/` | notes, tasks, activities, activity_participants | 备注/待办 CRUD；**活动与联系人一对多，经参与者表关联**（2026-09-21 定稿）、联系人时间线聚合 | L3 |
| L3 礼物 | gifts | `app/modules/gifts/` | gifts, wishlist_items | 礼物往来（送出/收到）与愿望清单（未送出，open/purchased/given 状态机）两个状态域；独立管理页 + 搜索；愿望送出可转礼物记录（converted_gift_id 回链） | L3 |
| L3 资金 | funds | `app/modules/funds/` | fund_flows | 资金往来与借贷记账（方向/类别/金额/应收还日/结清状态）；`due_at` 未结清 = 主页"还款提醒"待办源；独立管理页 + 搜索 | L3 |
| L3 配置 | settings | `app/modules/settings/` | app_settings | 运行时配置读写（LLM/Embedding/高德 key，D6.2/D14） | 骨架 ✅ / 页面 L4 |
| L3 提醒 | reminders | `app/modules/reminders/` | reminders | **主动提醒引擎（D22）**：三源扫描（重要日期/任务/还款，口径复用各源既有 service 函数）、幂等重建（UNIQUE(user,source,ref,due) 已读不复活、源头消失清理）、进程内 asyncio scheduler（1h）、应用内通知（邮件 provider 位预留）；供首页徽标与提醒页消费 | ✅ |
| L4 聚合 | dashboard | `app/modules/dashboard/` | **无表，只读聚合** | 主页：待办分类聚合（日期提醒/待办任务/还款提醒=funds 到期，**分类可扩展**）、联系统计与后续人情统计增量（未结清借款、年度送礼支出…）、跳转过滤契约 | 当前 |
| L4 智能 | ai | `app/modules/ai/` + `backend/agent/` | pending_actions, embeddings（pgvector 1024 维，元数据关联业务 id）, ai_sessions | DeepAgents 封装（agent/ 目录，隔离上游）、`/mcp` 端点、结构化抽取、写入确认队列、语义检索、会话索引与会话业务（modules/ai/sessions.py）；视觉导入（图片随对话进 agent，识别产物走写入确认队列，D21） | L4 |

## 2. 依赖方向（import 只允许自上而下）

```
L0  core / permission                     （不依赖任何业务模块）
      ↑
L1  auth                                  （core）
      ↑
L2  contacts   geo                        （contacts → auth, permission, geo；geo → core）
      ↑
L3  graph   records   settings   reminders （contacts, auth, permission）
      ↑       ↑         ↑
L4  dashboard      ai                     （contacts/graph/records/settings…）
```

- `dashboard` 与 `ai` 是**纯消费叶子**：任何业务模块不得反向依赖它们；
- permission 被 L1–L4 全部业务模块依赖，图中省略；**settings 的读取**（`get_setting`）同为横切能力——各层经 settings service 公开函数读配置（如 geo 解析时由 contacts 传入高德 key），写入仍独占于 settings 模块；
- `geo` 是纯函数模块（静态表内置、外部 HTTP 封装、配置注入），无表无状态，被 contacts 在保存流程中消费；
- `backend/agent/`（DeepAgents 封装）属 ai 模块的可替换实现层，业务代码禁止直接 import deepagents（D6.1）。

### 依赖规则（违反即架构回退）

1. **表写权独占**：一张表的 INSERT/UPDATE/DELETE 只出现在它所属模块的代码里。
2. **跨模块读只有两种合法形态**：① 调对方 `service.py` 公开函数；② 本模块 repository 层 import 对方 `models` 做**只读 JOIN**（models 是共享数据契约，外键本来就跨表）。禁止摸对方 repository 函数、service 私有函数。
3. **service 是唯一业务门面**：跨模块业务调用只能走 `app/modules/<m>/service.py` 公开函数，或该模块显式导出的纯函数子模块（如 `contacts/calendar.py`）。
4. **依赖单向无环**：新模块登记时必须声明它依赖谁，出现环 = 设计错误，回退重划。
5. **先登记后实现**：新模块先在本文档第 1 节登记（表/职责/依赖/Level），再建包写代码。

## 3. 数据表归属与 FK 依赖

| 表 | 归属模块 | FK 指向 |
|---|---|---|
| families | auth | — |
| users.contact_id（D15，可空） | auth | contacts（账号锚定到联系人，FK 字符串引用无 import 依赖） |
| users | auth | families |
| user_tokens | auth | users |
| app_settings | settings | users（updated_by, nullable） |
| contacts | contacts | users, families |
| important_dates | contacts | contacts |
| relationship_types | graph | — |
| relationships | graph | contacts ×2, relationship_types, users |
| notes / tasks | records | contacts（contact_id nullable） |
| activities | records | —（参与者关联见下行） |
| activity_participants | records | activities（级联删）, contacts |
| gifts / wishlist_items | gifts | contacts（nullable）；wishlist_items → gifts（converted_gift_id nullable） |
| fund_flows | funds | contacts（nullable） |
| activity_images | records | activities（级联删）；**文件**删除由应用层在事务提交后执行 |
| pending_actions | ai | families, users |
| embeddings（L4 再建表） | ai | 逻辑引用 entity_type + entity_id，不设硬 FK |
| ai_sessions | ai | users（user_id）｜业务态，对话内容存于 checkpointer |

## 4. 对外接口地图（模块边界 = API 边界）

| 前缀 | 模块 | 端点（现有 / 计划） |
|---|---|---|
| /api/v1/uploads | uploads | ✅ `POST /uploads/temp`（上传到临时区）、`GET /uploads/tmp/{user_id}/{filename}`（仅本人可读） |
| /api/v1/auth | auth | ✅ `POST /auth/login`、`GET|PUT /auth/me`（绑定"我是谁"）、个人令牌管理 `POST|GET /auth/tokens` + `DELETE /auth/tokens/{id}`（D11，明文仅签发时返回一次） |
| /api/v1/contacts | contacts | 列表（tier/search/activity 过滤）、详情、创建、更新、升级、归档、同名检测、重要日期 CRUD（/{id}/dates）；计划：`GET /contacts/map-points`（地图页 choropleth+scatter 数据：坐标点 + 省份计数聚合） |
| /api/v1/graph | graph | ✅ 关系类型字典（读+自定义新增）、关系边（建/删/视角化列表）、`GET /graph/data`（递归 CTE N 度展开，全图/中心模式） |
| /api/v1/records | records | ✅ 活动（含参与者与**图片全量替换**，D18）/任务/备注 CRUD；`GET /activities/images/{id}?size=thumb|full`（鉴权读图）；`/activities` 支持 `contact_id`/`limit`/`offset`；备注可见性跟随联系人（私密联系人的备注对家人隐藏） |
| /api/v1/gifts | gifts | ✅ 礼物往来 + 愿望清单（`/gifts/wishlist/*`），搜索/过滤/转礼物 |
| /api/v1/funds | funds | ✅ 资金往来 CRUD + 结清状态机，多维过滤 |
| /api/v1/dashboard | dashboard | ✅ `GET /dashboard/todos?bucket=`（待办四桶 × 五源聚合）；`GET /contacts/{id}/timeline`（联系人时间线四源全量倒序，路由挂 /contacts 前缀但实现在本聚合模块）；`GET /dashboard/stats`（主页统计卡：总数/近30天/半年未联系/待办数，口径与名册过滤联动） |
| /api/v1/settings | settings | 运行时配置读写（页面 L4） |
| /api/v1/reminders | reminders | ✅ 列表（未读/全部）、未读数、逐条/全部已读、手动扫描（D22） |
| /api/v1/ai、/mcp | ai | ✅ SSE 对话（POST /ai/chat，请求带 `session_id`、缺失则服务端补；`images` ≤1 张本人临时图，服务端转 data URI 以多模态消息直通 agent）、会话列表 `GET /ai/sessions`、删除 `DELETE /ai/sessions/{id}`、历史 `GET /ai/sessions/{id}/messages`、写入提议确认（/ai/pending/*，含 create_contact）、工具清单（/ai/tools）、`/mcp` Streamable HTTP（对外，JWT 或个人令牌门卫）；agent 封装在 backend/agent/（deepagents 唯一 import 点）；`POST /ai/embeddings/rebuild`、`GET /ai/search?q=`（语义检索） |

## 5. 前端映射与组件规范

- **页面 ↔ 后端模块一一对应**：`pages/`（HomePage、ContactsPage、ContactDetailPage；L2 GraphPage、L4 SettingsPage/ChatPage）；`api/` 目录与后端模块同名对应（api/dashboard.ts…），契约经 openapi-typescript 生成，前端禁止绕过契约。
- **组件规范（2026-09-22 用户指令，D13；替代 2026-09-21 的 Naive UI 指令）**：组件框架 = **Element Plus**，图表框架 = **ECharts（锁 5.x）+ echarts-gl**；直接组合组件库现成组件，**不重复造自研基础组件**，仅无对应形态时才自研（如 ContactAvatar、graphGL 图容器）；Element Plus 视觉经 **CSS 变量映射层**（`design/` 内把 `--el-*` 翻译为 design tokens）收敛，ECharts/echarts-gl 的主题色同样只消费 tokens，业务组件禁止硬编码样式常量。
- 视觉事实源不变：`DESIGN.md` + `frontend/src/design/`；**页面内容宽唯一口径**是全局 `.crm-page`（画布型布局页用 `.crm-page--full` 豁免），**数据录入统一居中弹窗**（D16/D17，2026-09-25）。

## 6. 唯一口径（每条规则全系统只有一个实现点）

| 口径 | 唯一实现点 |
|---|---|
| 权限判定（读/写） | `app/services/permission.py` |
| 展示名 display_name | `contacts.models.Contact.display_name` 属性 |
| 农历↔公历、日期下次发生日 | `contacts/calendar.py`（lunar-python 封装） |
| "最近联系时间"（联系人维度） | contacts repository 的 last_activity 只读子查询；名册过滤（recent_30d/stale_180d）与 dashboard 统计共用同一实现 |
| 文件存储（临时区/正式区/缩略图/路径安全） | `app/services/storage.py` |
| 列表分页与总数口径 | 各模块 repository 的 `find_*` 与 `count_*` 成对实现（过滤条件必须一致）；HTTP 层 limit 默认 20、上限 200 |
| 展示层禁止重复实现以上口径，只消费接口结果 |

- `GET /contacts/{id}/timeline` 聚合接口**保留供 AI 工具 `get_contact_timeline` 使用**；前端往来区已改为按 Tab 分别调用三个列表接口（D19）。

## 7. 本次主页（dashboard）落点

0. **模型修正先行（2026-09-21 用户定稿触发）**：Alembic 迁移——`activities` 弃用 contact_id 改经 `activity_participants` 关联（存量数据迁移为参与者行），并按"建表先行"纪律创建 `gifts` / `wishlist_items` / `fund_flows` 三表（功能 L3 落地）；主页统计的"最近联系时间"子查询建立在参与者表上，避免下一轮再改口径。
1. **graph 模块就位**：relationship 模型自 contacts 迁入 `app/modules/graph/`（表结构不变，无需迁移），提供 `GET /graph/data` 最小读接口——主页 3D 预留区先以真实数据占位渲染，L2 图谱页复用同源数据。
2. **contacts 增强**：`calendar.py` 历法引擎 + `upcoming_dates()`（待办"日期提醒"源）+ `contact_stats()` 与列表 `activity` 过滤（统计与名册跳转同口径）。
3. **records 最小面**：先建 `records/service.py` 只读函数（到期任务），供 dashboard 聚合；CRUD 端点留 L3。
4. **dashboard 模块**：`GET /dashboard` 返回 `{todos: 分类待办, stats: 统计}`，无表、纯聚合；待办本轮出"日期提醒 / 待办任务"两类，**"还款提醒"分类结构预留**，待 funds 模块（下一轮）接入 `fund_flows.due_at` 未结清数据。
5. **前端 HomePage**：Naive UI 组件组合——待办分组列表 + 统计卡（点击带 `?activity=` 跳名册）+ 右半区 3D 图预留卡片（graph 真数据、L2 接渲染引擎）；路由默认落 `/home`。
