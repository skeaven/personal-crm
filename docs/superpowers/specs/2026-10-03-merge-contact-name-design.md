# 联系人姓名模型合并为单字段（name）设计

> 日期：2026-10-03｜状态：待用户审阅
> 上游：`PROJECT_BACKGROUND.md`（R1 中文本地化，其「姓、名分离存储」条目本次改写）、`DATA_MODEL.md` 第 2 节、`TECH_DECISIONS.md`（本次登记 D23）
> 本文是实施计划的输入；批准后进入 `writing-plans`。

## 1. 目标（用户原话拆解）

用户原话：「中文的姓名是一个字段存储的，现在的系统被拆成了两个，合成一个方便存储和检索」，并明确「系统就存储一个 name 和一个 nickname，nickname 是中文的外号或者亲近的称呼」。

1. `contacts` 表姓名**单字段存储**：`name`。
2. 姓名模型收敛为 `name` + `nickname` 两个字段——`display_name_override` 一并删除。
3. 存储与检索口径随之简化：搜索、同名检测、AI 建人都不再需要拆分姓/名。

**明确放弃的能力**（用户已知悉并确认）：姓氏排序、按姓氏生成称呼。当前代码无任何一处单独使用「姓」（`graph/kinship.py` 的称谓走角色路径，不碰姓氏），故当下零功能损失。

## 2. 现状核对

| 项 | 现状 |
|---|---|
| 存储 | `last_name VARCHAR(50)` + `first_name VARCHAR(50)`，均 NOT NULL DEFAULT '' |
| 展示名 | `display_name` model property（唯一实现点）：`display_name_override > nickname > 姓+名 > 名 > "（未命名）"` |
| 搜索 | `repository.find_contacts`：`last_name.ilike OR first_name.ilike OR nickname.ilike OR display_name_override.ilike` |
| 同名检测 | `repository.find_family_duplicates`：`Contact.last_name + Contact.first_name == full_name` 字符串拼接后全等比较 |
| 覆盖名 | `display_name_override` 穿在 model/schema/types 里，**前端无任何填写入口**（死字段） |
| 姓氏独立用途 | **无**。无姓氏排序、无按姓生成称呼 |
| 索引 | `DATA_MODEL.md:80` 声明的 `search_text` 生成列 + pg_trgm GIN **从未实现**（全仓无命中），本次仅修正文档描述 |
| 文档冲突 | `PROJECT_BACKGROUND.md:95` 原需求为「姓、名分离存储但符合中文习惯」，与本次决策相反，需改写 |

## 3. 关键决策（登记为 TECH_DECISIONS D23）

1. **单字段存储，彻底删除姓/名两列**（而非只统一检索口径，也非保留派生姓氏列）。中文姓名本就是一个整体，拆分只带来录入时的边界猜测成本；检索收益（搜索/查重各简化一处）随之落地。
2. **一并删除 `display_name_override`**。它是无填写入口的死字段，且与 `nickname`（外号/亲近称呼）职责重叠；姓名模型收敛为 `name` + `nickname`。
3. **硬切，不留兼容层**。单仓自托管、前端是唯一消费者；兼容期只会让两个字段多活一个版本。`/mcp` 的 `create_contact` 工具契约同步变更（工具 schema 由 `tools/list` 动态下发，无缓存问题）。
4. **迁移向上拼接、向下不可逆**。整名无法可靠拆回姓/名，迁移文件显式注释该限制。

## 4. 后端设计

### 4.1 数据模型（`contacts` 表）

| 动作 | 列 | 定义 |
|---|---|---|
| 加 | `name` | `VARCHAR(100) NOT NULL DEFAULT ''`，注释「姓名（中文姓名整体存储，D23）」 |
| 删 | `last_name` | — |
| 删 | `first_name` | — |
| 删 | `display_name_override` | — |
| 不动 | `nickname` | `VARCHAR(100) NULL`，语义明确为外号/亲近称呼 |

长度取 100：原 `50 + 50` 的上界，不缩水（复姓、外国长名都有余量）。
`NOT NULL DEFAULT ''` 保持不变——edge 联系人允许只有昵称，最小信息集由 schema 校验而非 DB 约束兜底。

`Contact.display_name` property 简化为：

```
nickname（非空则取，strip）> name（strip）> "（未命名）"
```

### 4.2 迁移

新 revision（`down_revision = b8e9d4f3a276`，文件名 `<rev>_merge_contact_name_d23.py`）：

`upgrade`：
1. `add_column("contacts", name ...)`
2. `UPDATE contacts SET name = coalesce(last_name,'') || coalesce(first_name,'')`
3. `drop_column` × 3（`display_name_override`、`first_name`、`last_name`）

`downgrade`（不可逆，迁移文件内注释说明）：
1. `add_column` 还原三列
2. `UPDATE contacts SET last_name = name`（整名整体存入 `last_name`，`first_name` 置空）
3. `drop_column("contacts", "name")`

PostgreSQL 原生支持 `ADD/DROP COLUMN`，不使用 batch 模式。

### 4.3 契约（破坏性变更）

| 位置 | 变更 |
|---|---|
| `ContactBase`（schemas.py） | `last_name`/`first_name`/`display_name_override` → `name: str = Field(default="", max_length=100)` |
| `ContactCreate.validate_name_presence` | 改为 `name`、`nickname` 至少一项；错误文案「姓名、昵称至少填写一项」 |
| `ContactUpdate` | 同上三字段 → `name: str \| None = Field(default=None, max_length=100)` |
| `ContactOut` | 同上三字段 → `name: str` |
| `GET /contacts/duplicate-check` | 查询参数 `last_name`+`first_name` → `name` |

`display_name` 仍由 `ContactOut` 输出（服务端计算），前端列表渲染不变。

### 4.4 检索与同名检测简化

- `find_contacts` 搜索条件降为两项：`Contact.name.ilike(pattern) | Contact.nickname.ilike(pattern)`
- `find_family_duplicates` 签名 `last_name, first_name` → `name`；匹配条件降为 `Contact.name == name.strip()`
- 行为只会变准：此前「陈」+「建国」与「陈建」+「国」都会拼成「陈建国」而误判同名，现在只有真输入一致才命中
- `service.check_duplicates` / `create_contact` 的传参同步

### 4.5 AI / MCP 工具契约（`ai/registry.py`）

- `CreateContactArgs`：`last_name`+`first_name` → `name: str = Field(default="", max_length=100)`；validator 与 `ContactCreate` 保持同一最小信息集
- `_run_queue_create_contact` 的 payload：`"name": args.name` 取代两个键
- 回执文案：`f"{args.last_name}{args.first_name}{args.nickname or ''}"` → `args.name`，昵称非空时以 `（昵称）` 形式跟随

### 4.6 种子数据

`backend/scripts/seed.py` 7 处联系人构造：`last_name="陈", first_name="建国"` → `name="陈建国"`（昵称、层级、可见性等不动；`colleague_son` 本就只有 nickname，不受影响）。

## 5. 前端设计

| 文件 | 变更 |
|---|---|
| `src/api/types.ts` | `Contact` / `ContactCreate` / `ContactUpdate` 三处字段替换（**不保留**旧字段的可选残留） |
| `src/api/contacts.ts` | `duplicateCheck` 参数 `{ last_name?, first_name?, nickname? }` → `{ name?, nickname? }` |
| `src/pages/ContactsPage.vue` | 建人弹窗「姓」「名」两个 `el-form-item` 合并为一个「姓名」（placeholder「如：陈建国」）；`form` 初值、`isSubmittable`、重置逻辑同步 |
| `src/pages/ContactDetailPage.vue` | 编辑弹窗同上去两框为一框；`editDraft` 初值、提交、重置同步；详情页姓名行 `{{ contact.last_name }}{{ contact.first_name \|\| '—' }}` → `{{ contact.name \|\| '—' }}` |
| `src/components/AgentChat.vue` | 确认面板中文标签映射：删 `last_name: '姓'`、`first_name: '名'`，加 `name: '姓名'` |

列表页姓名列**不动**——渲染 `row.display_name`。样式无新增，不涉及 design tokens。

## 6. 测试

TDD 顺序：先改写失败用例 → 再改实现 → 全绿。

`backend/tests/test_contacts.py`（主要战场，新增/改写）：

1. 搜索「建国」命中 `name="陈建国"`（单字段模糊匹配）
2. 同名检测：`name` 全等命中 → `created=False` + warnings；`confirm_duplicate=True` 时放行落库
3. `name` 与 `nickname` 均为空 → 422
4. `display_name` 规则：有 nickname 取 nickname；无 nickname 取 name；皆无 → 「（未命名）」

其余 15 个后端测试文件为机械替换（`last_name="张", first_name="三"` → `name="张三"`）：
`test_ai_chat` / `test_ai_pending` / `test_ai_tools` / `test_contact_location` / `test_dashboard` / `test_dates` / `test_funds` / `test_gifts` / `test_graph` / `test_kinship_api` / `test_notes` / `test_records` / `test_semantic` / `test_stats` / `test_timeline`

前端：`frontend/tests/agentChat.spec.ts` 标签映射用例同步。

## 7. 文档同步（事实源，改动前登记）

| 文档 | 变更 |
|---|---|
| `TECH_DECISIONS.md` | 新增 **D23**：姓名单字段存储；记录放弃姓氏排序/按姓称呼的代价 |
| `DATA_MODEL.md` | 第 2 节字段表（三列 → `name`）；第 80 行索引说明修正（`search_text` 从未实现，改为当前真实索引口径）；第 82 行展示名规则改写 |
| `PROJECT_BACKGROUND.md:95` | R1 姓名条目由「姓、名分离存储」改写为「姓名整体单字段存储」 |
| `ARCHITECTURE.md` 第 6 节 | 展示名口径一行的规则描述同步（实现点位置不变：`contacts.models.Contact.display_name`） |
| `ROADMAP.md:40` | 联系人条目「中文姓名模型」描述同步 |

`docs/superpowers/specs/2026-09-29-vision-import-design.md` 是带日期的历史 spec，不改写，由本 spec 接续（其 4.4 节的 `last_name`/`first_name` 描述已过期）。

## 8. 影响面清单

后端生产代码 8 个文件：`contacts/{models,schemas,repository,service,api}.py`、`ai/registry.py`、`alembic/versions/<rev>_merge_contact_name_d23.py`、`scripts/seed.py`
后端测试 16 个文件（`test_contacts.py` 为主战场 + 15 个机械替换）、前端 6 个文件、文档 5 个文件。

## 9. 验收标准

1. 全新库跑 `alembic upgrade head` 后 `contacts` 表只有 `name`/`nickname`，无 `last_name`/`first_name`/`display_name_override`
2. 存量库升级后，原「陈」+「建国」变为 `name="陈建国"`，条数与其它字段不变
3. `uv run pytest` 全绿；`uv run ruff check .` 干净；`npm run test`、`npm run build` 通过
4. 手工核验：建人表单只有一个姓名框，能创建、能搜到、同名提示仍生效
5. `/mcp` 的 `create_contact` 工具入参为 `name`，提议-确认全链路可用
