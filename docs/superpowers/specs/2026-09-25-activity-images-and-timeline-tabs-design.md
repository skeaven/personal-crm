# 活动图片 + 联系人往来改 Tabs 设计

> 日期：2026-09-25｜状态：待用户审阅
> 上游：`PROJECT_BACKGROUND.md`、`TECH_DECISIONS.md`（D10 附件存储本次落地为 D18）
> 本文是实施计划的输入；批准后进入 `writing-plans`。

## 1. 目标（用户原话拆解）

1. 活动新建/编辑时可添加**多张**图片，**默认第一张**显示在联系人详情页的往来区域。
2. 联系人往来的**所有卡片**提供「删除」与「查看详情」。
3. 「查看详情」与对应列表页的弹窗**复用同一组件、行为一致**。
4. 弹窗内可直接编辑并保存。
5. 往来区域改为 **Tabs**（活动 / 资金往来 / 礼物往来三个 tab），不再依赖聚合接口，支持**分页瀑布流加载**。
6. 保存按钮交互规范（用户补充）：**默认置灰**，**有改动才可点**；关闭/取消**不落库**；保存成功弹**几秒后消失的气泡**。

## 2. 已确认的关键决策

| # | 决策 | 来源 |
|---|---|---|
| 1 | 图片存**本地卷**，路径走配置项 `UPLOAD_DIR`；开发环境指向项目目录（`backend/uploads/`），容器内为 `/app/uploads` + named volume。DB **只存相对路径** | 用户 |
| 2 | 图片访问需**登录态**，走**鉴权端点**（不静态挂载、不靠 UUID 保密） | 用户 |
| 3 | **两阶段上传**：先 `POST` 上传到**临时目录**拿路径 → 表单提交时 JSON body 里带这些路径 → 真正保存时才从临时目录移入正式存储。**表单提交统一 JSON body**（不用 multipart） | 用户 |
| 4 | 往来改三个 Tab；**保留竖向时间线视觉**；每个 tab 提供**新建按钮** | 用户 |
| 5 | 保存按钮：脏检查决定可用性 + 必填校验叠加 | 用户 |
| 6 | 共享表单组件抽**三个**（活动/礼物/资金，即时间线三源）；心愿/待办/名册三个弹窗不抽，但同样上脏检查 | 用户确认范围 |

### 2.1 与用户判断不同的一点（已澄清）

用户提出「这样不需要聚合接口」。核实后：`build_contact_timeline` 除前端外还被 **AI 工具 `get_contact_timeline`** 使用（`ai/registry.py:129`，有 `test_ai_tools.py` 覆盖）。

**结论**：聚合服务函数与 `GET /contacts/{id}/timeline` 端点**保留不动**（AI 工具的能力面），**仅前端停止调用**。前端改用三个列表接口后，`TimelineItemOut` 也无需新增 `owner_user_id`——三个业务 Out 契约本就带该字段。

## 3. 后端设计

### 3.1 存储层：`app/services/storage.py`（L0 横切，唯一文件存储实现点）

与 `services/permission.py` 同级，无表无状态、配置注入、可独立测试。

- 目录布局（`UPLOAD_DIR` 之下）：
  - `tmp/{user_id}/{uuid}.{ext}` —— 临时区，未提交的上传
  - `activities/{yyyy}/{mm}/{uuid}.{ext}` —— 正式区
- 职责：`save_temp()` / `promote_temp()`（临时→正式，含缩略图生成）/ `delete()` / `resolve_path()`（**路径穿越校验**：解析后必须落在 UPLOAD_DIR 内，拒绝 `..` 与绝对路径）/ `cleanup_temp()`（清理超 24h 的孤儿临时文件，应用启动时执行一次）。
- **新增依赖：`pillow`（12.3.0，2026-09-25 经项目源解析确认的最新稳定版）**。项目当前无任何图像库；缩略图不做就只能让时间线加载 10MB 原图。
- 缩略图：用 Pillow 生成长边 400px 的 `{uuid}.thumb.jpg`，时间线卡片用缩略图、点开看原图。没有它，一屏几张手机原图会明显卡。
- 限制：jpg/png/webp，单张 ≤10MB，每活动 ≤20 张。**HEIC 明确不支持**（手机直出格式），前端给可见提示；要支持需再引入解码库，本次不做。

### 3.2 数据表：`activity_images`（归 records 模块，写权独占）

| 列 | 说明 |
|---|---|
| `id` | PK |
| `activity_id` | FK activities，**级联删** |
| `path` | 相对路径（`activities/2026/09/xx.jpg`） |
| `thumb_path` | 缩略图相对路径 |
| `sort_order` | 展示顺序，升序；**最小者为时间线封面** |
| `created_at` | TimestampMixin |

登记到 `ARCHITECTURE.md` 第 3 节（归属 records）。迁移一条。

### 3.3 接口变更

| 端点 | 变更 |
|---|---|
| `POST /api/v1/uploads/temp` | **新增**。multipart 单文件 → `{temp_path}`。落 `tmp/{当前用户}/`，文件名服务端生成（不信任客户端文件名） |
| `GET /api/v1/uploads/tmp/{user_id}/{filename}` | **新增**。仅本人可读（`user_id != current_user.id` → 404） |
| `GET /api/v1/records/activities/images/{image_id}` | **新增**。查图 → 定位所属活动 → 复用现有 `get_readable_activity` 判可见性 → 返回文件。`?size=thumb\|full`（默认 full） |
| `POST/PATCH /records/activities` | body 新增 `images` 字段（见下）；响应新增 `images: [{id, url, thumb_url, sort_order}]` |
| `GET /records/activities` | 新增 `contact_id` 查询参数（当前只有 search，三个接口里唯一缺的） |
| `GET /records/activities`、`/gifts`、`/funds` | 新增 `limit`（**默认 20**，上限 200）与 `offset`（默认 0）；响应新增 **`X-Total-Count`** 头 |

**图片字段语义（全量替换，与既有 `participant_ids` 约定一致）**：

```json
images: [
  {"id": 12},                                  // 保留已有（数组顺序即展示顺序）
  {"temp_path": "tmp/1/a1b2.jpg"}              // 新增
]
```
不在此数组中的已有图 → 删除（同时删文件）。`ActivityCreate` 只允许 `temp_path` 项。

**提交侧校验（安全关键，不能只靠临时读取端点兜底）**：

1. 每个 `temp_path` 必须落在 **`tmp/{当前用户 id}/`** 之内，否则拒绝——防止把他人临时文件"认领"进自己的活动。
2. 每个保留项 `{"id": n}` 必须属于**本活动**，且本活动对当前用户可写（`ensure_can_write`），否则拒绝——防止把他人图片挂到自己的活动上。
3. 所有路径经 `storage.resolve_path()` 归一化并校验落在 `UPLOAD_DIR` 内。

**分页（保守默认，用户 2026-09-25 指令）**：

- **不传 `limit` 就是 20 条**，不存在"不传即全量"的旁路——避免任何调用方无意间拉全表。传了则按传的来，**上限 200**（防 `limit=999999` 绕过）。
- 响应体**仍是数组**，不改 `{items,next_cursor}` 结构以保持契约稳定；总数走 **`X-Total-Count` 响应头**（总是返回）。时间线用「返回条数 < limit」判断到底、忽略该头；列表页用它算总页数。
- 该默认值只作用于 HTTP 层。service 层函数保持原语义，因此 **AI 工具与主页聚合（走 service 层）完全不受影响**。
- `// ponytail: offset 分页，个人 CRM 量级够用；滚动中若有他人新增会跨页重复，届时换 keyset`

排序**沿用各 repository 现状**，不另起口径：gifts `given_at desc nulls_last, id desc`；funds `occurred_at desc, id desc`；activities `occurred_at desc nulls_last, id desc`。无日期的记录稳定排在末尾。

### 3.4 事务与文件一致性

文件操作**在 DB 提交之后**执行（先事务、后落盘/删盘）。失败时文件成为孤儿，由 `cleanup_temp` 与后续巡检兜底；反过来（先动文件后提交失败）会留下 DB 指向不存在文件的坏数据，更难修。

### 3.5 删除路径的文件清理

DB 行由 `activity_images` 的级联删处理，但**文件不会被级联删**：

- **删除活动**：service 在事务提交后，按删除前查出的路径逐个删文件。
- **替换图片**（全量替换语义中被移除的那些）：同样在提交后删文件。
- 两步都可能因进程中断留下孤儿文件，由 `cleanup_temp` 与后续巡检兜底——这与 3.4 的取向一致：宁可留孤儿文件，也不留指向不存在文件的 DB 行。

## 4. 前端设计

### 4.1 新增/改动清单

| 文件 | 作用 |
|---|---|
| `composables/useFormDirty.ts` | **唯一脏检查实现点**：快照对比 + 「有改动 && 必填通过」才可保存 |
| `composables/useAuthedImage.ts` | 鉴权图片加载：带 Bearer 取 blob → `objectURL`，缓存与释放（`revokeObjectURL` 防泄漏） |
| `components/ImageUploader.vue` | 选图 → 调临时上传 → 缩略图列表（可删、可拖拽排序，首张标「封面」） |
| `components/ActivityFormDialog.vue` | 活动表单（含 `ImageUploader`），列表页与详情页共用 |
| `components/GiftFormDialog.vue` / `FundFormDialog.vue` | 同上，礼物/资金 |
| `components/RecordTimeline.vue` | 单个 tab 的竖向时间线 + 哨兵无限滚动 + 卡片操作 |
| `pages/ContactDetailPage.vue` | 「往 来」区块改为 `el-tabs`，三个 tab 各挂一个 `RecordTimeline` |
| `pages/ActivitiesPage/GiftsPage/FundsPage.vue` | 改用共享弹窗组件；上脏检查；表格加 `el-pagination` 页码分页 |
| `api/records.ts`、`api/gifts.ts`、`api/funds.ts` | `list()` 支持 `limit` / `offset`，并回传 `X-Total-Count` |
| `pages/TasksPage/WishlistPage/ContactsPage.vue` | 仅上脏检查（弹窗不抽） |
| `api/client.ts` | 支持 `FormData` 上传（现在写死 `Content-Type: application/json`，且不能手动设 boundary） |

图片展示优先用 Element Plus 官方 `el-image` + `el-image-viewer`（D16 组件形态优先），`src` 喂 `useAuthedImage` 产出的 blob URL。

### 4.2 交互

- **Tabs**：懒加载（首次切到才请求）；已加载的 tab 缓存；切回不重新拉。
- **瀑布流**：每个 tab 独立维护 `offset` 与已加载列表，哨兵进入视口追加下一页（复用现有 `IntersectionObserver` 写法）。
- **列表页分页**：三个管理页的 `el-table` 配 `el-pagination`（页码式，每页 20 条与后端默认一致），总页数取自 `X-Total-Count`；**搜索或筛选条件变化时重置回第 1 页**（否则会停在越界页看到空表）。
- **卡片操作**：右下角「查看详情」「删除」。删除走 `el-popconfirm`，**仅记录人本人可见**（与现有「关系」表格规则一致）；查看详情打开对应共享弹窗。
- **新建**：每个 tab 头部一个按钮（如「记一笔活动」），打开同一共享弹窗（新建态），当前联系人作为默认关联/参与者。
- **保存**：默认置灰 → 有改动且必填通过才可点 → 保存成功 `ElMessage` 气泡 + 关闭弹窗 + **重载当前 tab**。取消/关闭不落库、不请求。
- **图片**：活动弹窗内可多选上传，首张即封面；时间线卡片显示封面缩略图，点击开大图查看器（可左右翻看该活动其余图片）。

## 5. 测试策略（TDD）

- **后端**：`storage.py` 纯函数（含**路径穿越拒绝**用例）；临时上传→提交→落正式区的完整链路；跨用户读图返回 404；图片全量替换语义（保留/新增/删除混合）；`activities?contact_id=` 过滤；分页契约——**不传 `limit` 返回 ≤20 条**、`limit` 超上限被截断、`offset` 翻页不重不漏、`X-Total-Count` 与总数一致。
- **前端**：`useFormDirty` 单测（无改动不可保存 / 改动可保存 / 必填为空仍禁用 / 新建态空表单禁用）；现有 `design.spec.ts` 保持绿灯。
- 每步先写失败测试再实现；完成前跑 `uv run pytest && uv run ruff check .` 与 `npm run test && npm run build`。

## 6. 配置与部署

- 新增 settings 项 `upload_dir`；`backend/.env.example` 同步。
- `docker-compose.yml`：`uploads_data` named volume 挂到 `/app/uploads`，环境变量 `UPLOAD_DIR=/app/uploads`。
- `.gitignore` 加 `backend/uploads/`。
- 开发环境不额外配置即可用（默认指向项目内目录）。

## 7. 文档同步（AGENTS.md 硬约束）

- `TECH_DECISIONS.md`：**D10 由 ⬜ 转为 ✅**（本地卷）；新增 **D18 图片存储与两阶段上传**、**D19 联系人往来 Tabs 化**，并更新决策总览表。
- `ARCHITECTURE.md`：第 1 节登记 `app/services/storage.py`（L0 横切）与 `activity_images` 表归属；第 3 节表归属；第 4 节接口地图；第 6 节唯一口径加「文件存储」。
- `DATA_MODEL.md`：补 `activity_images` 字段级定义。
- `DESIGN.md`：图片上传组件与时间线的视觉规则（缩略图尺寸、封面标记）。

## 8. 不做的事（明确排除）

- 不抽心愿/待办/名册的弹窗组件（不在时间线上，非必要扩散）；但它们同样上脏检查规范。
- 不改聚合接口与其 AI 工具消费者。
- 不支持 HEIC；不做图片裁剪/滤镜；不做客户端压缩。
- 不做多文件并发上传的进度条（个人量级，逐张串行上传即可）。
