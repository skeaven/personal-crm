# MCP 工具面补齐：让 agent 与界面能力对等 设计

> 来源：2026-10-06 用户指令。起因是一次真实使用——用户要求"更新唐琴（id=39）的资料"，
> assistant 回答"我没有修改联系人的工具，只能新建"，并提示"别再确认编号 3，否则会出现两条唐琴"。
> 这不是模型能力问题，是**工具面只有 create、没有 update/delete**，模型被迫用新建模拟修改。
>
> 用户目标原话：「我期望的是能够用 ai 完成所有的增删改查业务，也就是说完全使用 agent
> 作为唯一入口也能正常使用这个系统」。

## 0. 已确认的四个决定（2026-10-06 用户回答）

| 问题 | 决定 |
|---|---|
| 「唯一入口」的含义 | **能力对等**：界面上能做的 agent 都能做，界面仍是主入口 |
| 删除的风险档位 | **不加档**：写入（含删除）一律进确认队列，规则无例外 |
| 覆盖范围 | **一次规划、分阶段落地**：contacts/records/gifts/funds/graph/reminders 全覆盖 |
| 设置类（API key）写入 | **不开放**：密钥只从界面输入，不进对话历史与待确认队列 |

## 1. 现状核对（已逐项核实源码）

- 工具单一实现源：`app/modules/ai/registry.py::ALL_TOOLS`（9 个）。
  `/mcp`（`mcp_endpoint.py::_register_all`）与内部助理（`agent/runner.py`）都从这里取，
  **补工具即两条入口同时生效，架构无需改动**。
- 写工具统一经 `pending_actions` 确认队列；`pending.py::EXECUTORS` 是「工具名 → 落库函数」
  的表，加一行即接入；`approve()` 的执行身份恒为提议人（D7）。
- 现有 9 个：读 6（`search_contacts` / `kinship_of` / `get_upcoming_todos` /
  `get_contact_timeline` / `semantic_search` / `get_stats`），写 3（`create_task` /
  `create_activity` / `create_contact`）。
- REST 侧约 50 个业务端点，agent 够得着 9 个。

三类缺口：
1. **改与删整体缺失**——所有写工具都是 `create_*`；
2. **三个模块零覆盖**——礼物（含心愿）、资金、备注；
3. **读不完整**——`search_contacts` 只回 id/展示名/tier/记录人，没有"按 id 读完整资料"
   的工具，模型看不到电话/地址/备注，也无法在改之前回读当前值（这正是它说
   "我无法帮你读回 id=39 里到底存了什么"的原因）。

另有两个既存摩擦点，本轮一并处理：
- 前端 `components/AgentChat.vue` 的 `TOOL_LABELS` 是**硬编码**的中文名映射
  （且为 `create_contact` 写了专用渲染器）。工具面扩到 47 个后不可维护。
- `registry.py::_resolve_contact_by_name` 在**多命中时静默取第一个**——同名/同音在中文
  人名里是常态，这是潜在的错误写入源。

## 2. 关键决策（登记为 TECH_DECISIONS D24）

### 2.1 工具组织：扁平 + 实体前缀（否决域聚合）

47 个工具平铺，命名 `<动词>_<实体>`；动词表固定为
`list / get / create / update / delete / promote / convert / mark`。

否决「按实体域聚合」（`contact(action, ...)`）与「高频扁平 + 低频聚合」两种混合方案：
前者的 schema 是字段并集，模型要同时选对 action 与字段，**出错率反而更高**，
且 pydantic 无法表达"删除时不该传字段"；后者让两套规则并存，模型与人脑都要记
"哪类用哪种"。本仓库整体风格是"显式优于灵活"（schema 分离、表写权独占、口径唯一），
域聚合的"灵活"正是它一直规避的东西。

代价与对策：`tools/list` 变长（约 4–6k token/轮）。对策是**描述即契约**——
每个工具的 description 必须写明"何时用我、何时用别人"，并纳入测试（见 §6）。

### 2.2 风险档位不变：`read` / `write_queue`

不新增 `destructive` 档，删除与建待办同一条队列。理由：规则无例外才不需要记例外；
且经真实使用验证，确认面板的成本可接受。

### 2.3 寻址统一为 `contact_id`（**破坏性变更**）

新工具一律用 `contact_id`；既有的三个按名字寻址的工具
（`create_task.contact_name` / `create_activity.participant_names` /
`get_contact_timeline.contact_name`）**同步改为 id**，不留兼容层。

理由：id 无歧义，且模型总能先经 `search_contacts` 拿到 id；按名字寻址在多命中时
静默取第一个（见 §1），是错误写入源。`participant_names` 因是多值，改为
`participant_ids`。

破坏性影响：外部 MCP 客户端的工具 schema 变化。工具 schema 由 `tools/list` 动态下发、
无客户端缓存问题，客户端重连即拿到新形状（同 D23 对 `/mcp` 的处置）。

### 2.4 设置类不开放

Agent 不获得任何 `app_settings` 写入工具（连提议工具也不开）。
`app_settings.value` 存的是 LLM/Embedding/高德 API key（明文，界面仅掩码回显）；
一旦经工具写入，密钥会同时落进 `pending_actions.payload`、确认面板渲染、
以及会话 checkpointer 的对话历史——三处全是明文。设置页仍是唯一入口。

### 2.5 label 下移到 `AiTool`

`AiTool` 增加 `label: str`（中文名），经既有 `GET /ai/tools` 下发（`ToolOut`
同步加字段），前端删除硬编码映射。

**不下发到 MCP**：MCP 的 `tools/list` 是协议标准形状（name/description/inputSchema），
塞自定义字段会污染协议；label 只走内部端点，供前端渲染确认面板。

### 2.6 `pending_actions` 增加 `preview` 列

确认面板要能回答"**这条提议会把什么改成什么**"。create 类显示 payload 即可，
update/delete 必须显示现状与差异。

方案：新增 `preview JSONB NULL` 列，专放**渲染用快照**（update 存 before 值，
delete 存实体摘要），与 `payload` 分离——执行器无感，`payload` 语义不变。
备选（面板自己调 REST 读现状）被否：确认的那一刻读到的可能已不是提议时的状态。

## 3. 补齐清单（38 个新工具，加现有 9 个 = 47）

命名即接口；每个写工具的 description 必须写明"需用户确认后生效"。

### 读（11 个，`risk="read"`，直执行）

| 工具 | 入参要点 | 用途 |
|---|---|---|
| `get_contact` | `contact_id` | 读单人**完整资料**（含重要日期列表）；改之前的回读入口 |
| `list_contacts` | `tier?` `search?` `activity?` | 名册遍历（`search_contacts` 必须有关键词，覆盖不了"列出所有边缘联系人"） |
| `list_tasks` | `status?` `contact_id?` | 待办列表 |
| `list_activities` | `contact_id?` `limit?` | 活动列表 |
| `list_notes` | `contact_id?` | 备注列表（含正文） |
| `list_gifts` | `contact_id?` `direction?` | 礼物往来列表 |
| `list_wishlist` | `status?` `contact_id?` | 心愿清单 |
| `list_funds` | `contact_id?` `settled?` | 资金往来列表 |
| `list_relationships` | `contact_id?` | 关系边列表（建边前查重） |
| `list_relationship_types` | — | 关系类型字典（建边需选类型） |
| `list_reminders` | `unread_only?` | 提醒列表 |

### 写（27 个，`risk="write_queue"`，进确认队列）

| 模块 | 工具 |
|---|---|
| contacts（6） | `update_contact`、`delete_contact`、`promote_contact`、`add_important_date`、`update_important_date`、`delete_important_date` |
| tasks（2） | `update_task`（含 `status` 流转，"把这条待办标完成"）、`delete_task` |
| activities（2） | `update_activity`、`delete_activity` |
| notes（3） | `create_note`、`update_note`、`delete_note` |
| gifts（3） | `create_gift`、`update_gift`、`delete_gift` |
| wishlist（4） | `create_wishlist_item`、`update_wishlist_item`、`delete_wishlist_item`、`convert_wishlist_item`（愿望送出转礼物） |
| funds（3） | `create_fund`、`update_fund`、`delete_fund` |
| graph（2） | `create_relationship`、`delete_relationship` |
| reminders（2） | `mark_reminder_read`、`mark_all_reminders_read` |

**没有 `get_task` / `get_note` / `get_activity` / `get_gift` / `get_fund`**：
这五类的 `list_*` 已返回完整行（含全部字段与 id），再给单条 get 是冗余工具，
只会增加模型的选择负担（YAGNI）。`get_contact` 例外——`search_contacts` 刻意只回
摘要（11 个联系人 × 20 字段全塞进上下文是浪费），需要单人的完整资料。

## 4. 后端设计

### 4.1 `AiTool` 扩展

```python
@dataclass(frozen=True)
class AiTool:
    name: str
    label: str          # 新增：中文名，前端确认面板用（不下发 MCP）
    description: str
    risk: str
    args_schema: type[BaseModel]
    run: Any
```

### 4.2 执行器

新执行器一律**调用各模块 `service.py` 的公开函数**（ARCHITECTURE 第 2 节：表写权独占、
跨模块只能走 service 公开函数）。`EXECUTORS` 与 `ALL_TOOLS` 必须一一对应——
加一条断言测试（§6），防止"工具注册了但没有执行器"这种静默失败
（`approve()` 对未知工具只是记 `ok=False`，用户看到的是"提议失败"而非"系统缺实现"）。

### 4.3 preview 快照

写工具的 `run` 在处理函数里读一次当前实体，把渲染用快照经 `propose(preview=...)`
写进 `preview` 列。快照口径：`update_*` 只放**本次会改动字段**的原值
（与 payload 键取交集，未提及的字段不参与差异展示），`delete_*` 放实体摘要
（展示名/正文首行等一行可读文本），create 类不填。迁移：`alembic revision --autogenerate`。

### 4.4 同名解析改为显式报错

`_resolve_contact_by_name` 多命中时报 `BusinessError`（列出候选让模型消歧），
不再静默取第一个。统一改 id 寻址后该函数退居"兼容残留"，仅在必要处保留。

### 4.5 系统提示词增补

`agent/runner.py::SYSTEM_PROMPT` 增加改/删工具的使用纪律：
- 改之前先 `get_contact`（或对应 `list_*`）回读当前值，禁止凭空改写；
- 找不到既有实体时**先报告并询问**，不得改用 create 绕过（唐琴事故的正解）；
- 删除类操作要在回复里复述将被删除的对象。

## 5. 前端设计（AgentChat 确认面板）

- 删除 `TOOL_LABELS` 硬编码，改从 `GET /ai/tools` 的 `label` 渲染；
- 确认面板按 `preview` 渲染：
  - `update_*` → 字段级「原值 → 新值」两列；
  - `delete_*` → 「将删除：<实体摘要>」；
  - `create_*` → 维持现状（payload 直读，`create_contact` 保留专用中文标签渲染）；
- 样式只消费 `design/tokens.ts`（前端风格硬约束）。

## 6. 测试

- **契约测试**（新增 `tests/test_ai_registry.py`）：
  1. `ALL_TOOLS` 的 `name` 唯一、`label` 非空、命名符合 `<动词>_<实体>`；
  2. `EXECUTORS` 与写工具的集合**完全相等**（双向差集为空）；
  3. 每个工具的 `args_schema` 能构造并给出 JSON schema（`model_json_schema()` 不抛）；
  4. `GET /ai/tools` 返回条数 == `ALL_TOOLS` 条数。
- **服务层行为测试**：每个新执行器一个用例（真实 DB、打桩 service 边界），
  覆盖"成功落库"与"目标不存在 → 记 `ok=False` 不 500"两条路径。
- **不做 LLM 端到端测试**（需真实 key、不确定）。工具选择的正确性靠 description
  纪律 + 人工核验，不靠自动化断言。

## 7. 文档登记

- `TECH_DECISIONS.md` 新增 D24（本设计 §2 的六条决策）；
- `ARCHITECTURE.md` 第 4 节 `/mcp` 一行更新为"47 工具、读写分离、写全进队列"；
- `DATA_MODEL.md` 补 `pending_actions.preview` 列；
- `ROADMAP.md` 加一节"agent 能力对等"与分期。

## 8. 不做（本期明确排除）

- **设置类写入**（§2.4）；
- **`create_relationship_type`**（自定义关系类型）：属半配置数据，建错会污染字典，
  需要时在界面加；
- **`scan_reminders`**：扫描是内部调度职责，agent 不需要触发；
- **批量操作**：先不做批量改/删（确认面板的粒度是单条），需要时再议；
- **语义索引自动重建**：沿用现状（设置页手动重建），新实体的索引对账沿用既有管线。

## 9. 风险与取舍

| 风险 | 处置 |
|---|---|
| 47 个工具的 `tools/list` 变长，模型选择变难 | 描述即契约 + 命名纪律；每阶段落地后人工核验典型话术 |
| `contact_name → contact_id` 破坏外部 MCP 客户端 | 已在 §2.3 显式声明；schema 动态下发，客户端重连即恢复 |
| 确认队列的确认成本（多步任务要确认多次） | 接受。这是"不加档"决定的已知代价 |
| 写工具执行器从 3 增到 30 条，`pending.py` 会变长 | 按模块拆 `executors/` 子包（阶段 1 实施），保持单文件职责清晰 |

## 10. 分期（5 阶段，每阶段可独立验收）

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| **1. 基础设施** | `AiTool.label` + `/ai/tools` 下发 + 前端消费；`pending_actions.preview` 列与迁移；`AgentChat` 的 update/delete 渲染；契约测试；`pending.py` 拆 `executors/` | 现有 3 个写工具的确认面板仍正常；契约测试全绿；`EXECUTORS` 拆分后现有测试不变 |
| **2. contacts** | `get_contact`、`list_contacts` + 6 个写工具；`contact_name → contact_id` 硬切；提示词改/删纪律 | 对话完成"改唐琴电话""给唐琴加农历生日""把某人升级为直接联系人"，面板显示 diff |
| **3. records** | tasks/activities/notes 共 9 个工具 | "把这条待办标完成""改上周活动的参与者""删掉那条备注" |
| **4. gifts + funds** | gifts/wishlist/funds 的 3 个 `list_*` + 10 个写工具 | "记一笔随礼""把心愿标为已送出并转成礼物记录" |
| **5. graph + reminders** | 3 个 `list_*`（关系边/关系类型/提醒）+ 关系增删 + 提醒已读 | "张三是我爸的弟弟，记下来""把提醒都标已读" |

每阶段结束跑全量（后端 pytest + ruff、前端 vitest + build）并在开发环境浏览器核验；
每阶段的工具选择质量由用户实际使用后反馈，不达标就调整 description 再进下一阶段。
