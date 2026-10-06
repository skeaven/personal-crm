# MCP 工具面补齐（阶段 1–2）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 agent 能改动已有数据（而非只能新建），并把工具的中文名与「改什么/删什么」的差异渲染交还给后端下发。

**Architecture:** 工具面唯一来源是 `app/modules/ai/registry.py::ALL_TOOLS`，`/mcp` 端点与内部助理同源消费；写工具一律经 `pending_actions` 确认队列，`pending.py::EXECUTORS` 负责「工具名 → 落库函数」映射。本阶段给 `AiTool` 加 `label`、给 `pending_actions` 加 `preview` 快照列、把确认面板的中文名与差异渲染从硬编码改为下发，然后补齐 contacts 的读写工具并把寻址从名字硬切成 id。

**Tech Stack:** FastAPI + SQLAlchemy 2 async + Alembic + pytest（后端）；Vue 3 + Element Plus + vitest（前端）。

**Spec:** `docs/superpowers/specs/2026-10-06-mcp-tool-coverage-design.md`

## 本计划只覆盖阶段 1–2，这是刻意的

Spec 的 5 个阶段里，阶段 3–5（records / gifts+funds / graph+reminders，共 36 个工具）是**阶段 2 建立的模式的机械复用**（每个模块 = N 个读工具 + M 个写工具 + 执行器 + 测试），而阶段 1 会改动 `AiTool`、`pending.py`、确认面板这三处地基。在地基落地前写阶段 3–5 的代码级步骤，写出来的代码在阶段 2 结束时就已经对不上（例如执行器要从 `pending.py` 拆进 `executors/`）。因此阶段 3–5 待阶段 2 落地后另出计划，届时它们引用的是仓库里真实存在的文件，而不是预测的形状。

## Global Constraints

- **工具单一来源**：任何工具都必须登记在 `registry.ALL_TOOLS`；禁止在 `/mcp` 端点或 `agent/runner.py` 里另设工具路径。
- **写工具一律 `risk="write_queue"`**：无例外，删除也是（用户 2026-10-06 决定「不加档」）。
- **执行器只能调各模块 `service.py` 的公开函数**，不得直接摸 repository 或跨模块写表（`ARCHITECTURE.md` 第 2 节，违反即架构回退）。
- **方法必须写中文 docstring**，说明意图、参数、返回值与关键约束（`AGENTS.md` 代码规范）。
- **前端只准消费** `frontend/src/design/tokens.ts` 与 `theme.ts`，禁止硬编码颜色/圆角/字体/阴影。
- **测试库**是独立的 `personal_crm_test`（`tests/conftest.py` 已在 import `app` 前用 `setdefault` 覆盖 `DATABASE_URL`）。
- **TDD**：先写测试看它失败，再写最小实现；重构以测试绿灯为前提。

## Review Focus

以下是 spec 隐含、但任务里的常规测试不一定覆盖、且最可能真正咬到用户的输入与条件。每条都在后文对应任务里配了测试。

1. **改/删别人或已归档的联系人** —— 应失败（不可见按 404），绝不能静默改到不属于调用者的数据。（Task 8）
2. **`update_contact` 的 payload 混入不该改的字段**（`owner_user_id`、`family_id`、`id`）—— 应被 schema 挡下，不能越权改属主或家庭。（Task 8）
3. **提议引用的 id 已被删除/归档** —— 确认时应记 `result.ok=False` 让人看见失败，绝不能 500 把提议卡在 pending 再也处理不掉。（Task 8、Task 9）
4. **批量确认里有条目失败** —— 其余条目必须照常执行（每条独立事务），逐条记结果，不做整体回滚。（Task 6）
5. **`GET /ai/tools` 拿不到时** —— 确认面板仍可用（回退显示工具原名），不能因为标签加载失败就整块面板报错。（Task 2）

---

## 文件结构

**后端**

| 文件 | 职责 | 本计划中的变化 |
|---|---|---|
| `backend/app/modules/ai/registry.py` | 工具注册表唯一来源：schema + 档位 + 处理函数 | 加 `label` 字段；加 8 个 contacts 工具；删 `search_contacts` |
| `backend/app/modules/ai/api.py` | 助理 REST（工具清单、提议队列） | `ToolOut`/`PendingActionOut` 加字段 |
| `backend/app/modules/ai/pending.py` | 提议入队、状态机、确认执行 | `propose()` 加 `preview`；执行器迁出 |
| `backend/app/modules/ai/models.py` | `PendingAction` ORM | 加 `preview` 列 |
| `backend/app/modules/ai/executors/`（新建） | 「工具名 → 落库函数」映射，按模块分文件 | 从 `pending.py` 迁入 |
| `backend/app/modules/contacts/service.py` | contacts 业务门面 | 不改（工具直接调它） |
| `backend/agent/runner.py` | agent 图与系统提示词 | 提示词改写/删纪律与 id 寻址 |
| `backend/tests/test_ai_registry.py`（新建） | 注册表契约测试 | 全部新增 |
| `backend/tests/test_ai_tools.py` | 工具行为测试 | 加新工具用例、删 `search_contacts` 断言 |

**前端**

| 文件 | 职责 | 本计划中的变化 |
|---|---|---|
| `frontend/src/api/types.ts` | 契约产物唯一来源 | `ToolOut`/`PendingActionOut` 加字段 |
| `frontend/src/components/AgentChat.vue` | 对话 + 确认面板 | 删硬编码标签、加差异渲染与多选批量 |
| `frontend/tests/agentChat.spec.ts` | 组件测试 | 加确认面板用例、mock 补 `tools` |

---

## Task 0: 登记决策 D24（先登记再写代码）

`AGENTS.md` 的硬约束：「新增架构层面决策时必须同步登记到 `TECH_DECISIONS.md`」，
`CLAUDE.md` 的事实源表也要求「改动前先在对应文档登记」。本阶段的工具面扩张、
寻址硬切、preview 列都是架构级决策，所以先登记再动代码。

**Files:**
- Modify: `TECH_DECISIONS.md`（决策索引表 + 文末追加 D24 小节）
- Modify: `ROADMAP.md`（加一节「agent 能力对等」指向本计划）

**Interfaces:**
- Consumes: 无
- Produces: `TECH_DECISIONS.md` 的 D24 条目，后续任务的提交信息可引用它

- [ ] **Step 1: 追加 D24**

在 `TECH_DECISIONS.md` 的决策索引表末尾加一行：

```markdown
| D24 | **MCP 工具面补齐**：REST 端点 → 工具 1:1 映射（52 个），寻址统一 `contact_id` 硬切，写工具一律进确认队列，label 与 preview 由后端下发 | 🚧 | 2026-10-06 |
```

在文末（D23 之后）追加小节，内容与 `docs/superpowers/specs/2026-10-06-mcp-tool-coverage-design.md` 的 §2 六条决策一致，并注明「完整设计与清单见该 spec」。写法照既有 D20–D23 的格式：**背景 / 决策（编号列表）/ 理由 / 影响**。

- [ ] **Step 2: ROADMAP 加一节**

在「Level 5 — 迁移与打磨」之前插入：

```markdown
## Agent 能力对等（D24，2026-10-06 起）

**目标**：界面上能做的，agent 都能做——补到 REST 端点与 MCP 工具 1:1（52 个工具）。

| 阶段 | 内容 | 状态 |
|---|---|---|
| 1. 基础设施 | label 下发、preview 列、确认面板差异渲染 + 多选批量、契约测试、执行器拆包 | 🚧 |
| 2. contacts | 读工具 + 改/归档/升级 + 重要日期三件套、寻址硬切 id | ⬜ |
| 3. records + 待办页 | 记录类 13 个工具、`list_tasks`/待办板补 `contact_id`、活动页与待办页按人筛选 | ⬜ |
| 4. gifts + funds | 15 个工具、三页按人筛选 | ⬜ |
| 5. graph + reminders | 8 个工具、提醒页按人筛选 | ⬜ |

阶段 1–2 的实施计划：`docs/superpowers/plans/2026-10-06-mcp-tool-coverage-phase1-2.md`
```

- [ ] **Step 3: 提交**

```bash
git add TECH_DECISIONS.md ROADMAP.md
git commit -m "docs: 登记 D24（MCP 工具面补齐）与 ROADMAP 分阶段清单"
```

---

## Task 1: `AiTool.label` 与 `/ai/tools` 下发

**Files:**
- Modify: `backend/app/modules/ai/registry.py`（`AiTool` 定义与 9 个工具条目）
- Modify: `backend/app/modules/ai/api.py:46-53`（`ToolOut`）与 `list_tools`（约 213 行）
- Test: `backend/tests/test_ai_tools.py`

**Interfaces:**
- Consumes: 无（本任务是地基）
- Produces: `AiTool.label: str`（中文名，非空）；`GET /api/v1/ai/tools` 的响应体每项形如
  `{"name": str, "label": str, "description": str, "risk": str}`

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_ai_tools.py` 末尾：

```python
async def test_every_tool_has_label():
    """每个工具都有中文名：确认面板靠它渲染，前端不再自己维护一份映射。"""
    missing = [tool.name for tool in registry.ALL_TOOLS if not tool.label.strip()]
    assert missing == [], f"以下工具缺 label：{missing}"


async def test_tools_endpoint_exposes_label(client, login_headers, make_user):
    """GET /ai/tools 下发 label——它是前端渲染确认面板的唯一来源。"""
    _, password = await make_user(username="demo")
    headers = await login_headers("demo", password)

    response = await client.get("/api/v1/ai/tools", headers=headers)

    assert response.status_code == 200
    items = response.json()
    assert items, "工具清单不应为空"
    assert all(item["label"] for item in items), "每个工具都必须带 label"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_ai_tools.py -q -k label
```

预期：`AttributeError: 'AiTool' object has no attribute 'label'`

- [ ] **Step 3: 给 `AiTool` 加字段并填 9 个中文名**

`backend/app/modules/ai/registry.py` 的 dataclass 改为：

```python
@dataclass(frozen=True)
class AiTool:
    """MCP 工具三元组（D11）：schema + 风险档位 + 处理函数。"""

    name: str
    label: str  # 中文名：确认面板渲染用，经 /ai/tools 下发（不进 MCP 协议形状）
    description: str
    risk: str
    args_schema: type[BaseModel]
    run: Any
```

然后给 `ALL_TOOLS` 里的每个 `AiTool(...)` 紧跟在 `name=` 之后补一行 `label=`：

| name | label |
|---|---|
| `search_contacts` | `搜联系人` |
| `kinship_of` | `查称谓` |
| `get_upcoming_todos` | `查临近事项` |
| `get_contact_timeline` | `查往来` |
| `semantic_search` | `语义搜索` |
| `get_stats` | `查统计` |
| `create_task` | `建待办` |
| `create_activity` | `记活动` |
| `create_contact` | `建联系人` |

后三个与前端现有硬编码文案保持一致（`建待办` / `记活动` / `建联系人`），避免这一步产生视觉回归。

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && uv run pytest tests/test_ai_tools.py -q -k label
```

预期：2 passed（第二个用例此时仍会失败——`ToolOut` 还没有 `label`，见下）

- [ ] **Step 5: 让 `ToolOut` 与端点带上 label**

`backend/app/modules/ai/api.py` 中：

```python
class ToolOut(BaseModel):
    """MCP 工具清单条目（对外暴露的能力声明）。"""

    name: str
    label: str
    description: str
    risk: str
```

`list_tools` 的返回值补上 `label=tool.label`：

```python
    return [
        ToolOut(name=tool.name, label=tool.label, description=tool.description, risk=tool.risk)
        for tool in registry.ALL_TOOLS
    ]
```

- [ ] **Step 6: 跑测试确认通过**

```bash
cd backend && uv run pytest tests/test_ai_tools.py -q -k label
```

预期：2 passed

- [ ] **Step 7: 跑全量后端测试**

```bash
cd backend && uv run pytest -q && uv run ruff check .
```

预期：全绿（`ToolOut` 加字段是纯新增，无既有用例断言其精确形状）

- [ ] **Step 8: 提交**

```bash
git add backend/app/modules/ai/registry.py backend/app/modules/ai/api.py backend/tests/test_ai_tools.py
git commit -m "feat(ai): AiTool 增加 label，经 /ai/tools 下发中文名"
```

---

## Task 2: 前端消费 label，删掉硬编码映射

**Files:**
- Modify: `frontend/src/api/types.ts`（`ToolOut`，约 345 行）
- Modify: `frontend/src/components/AgentChat.vue`（`TOOL_LABELS` 常量与 `onMounted`）
- Test: `frontend/tests/agentChat.spec.ts`

**Interfaces:**
- Consumes: Task 1 的 `GET /ai/tools` 响应（每项含 `label`）
- Produces: 组件内 `toolLabels: Ref<Record<string, string>>` 与
  `labelOf(toolName: string): string`（拿不到标签时回退原名）

- [ ] **Step 1: 写失败测试**

在 `frontend/tests/agentChat.spec.ts` 里，把 `vi.hoisted` 与 `vi.mock` 补上 `tools`（组件接下来会调它，不补会让**现有用例**一起挂）：

```ts
const { chat, pendingList, tools, uploadTemp } = vi.hoisted(() => ({
  chat: vi.fn(),
  pendingList: vi.fn(),
  tools: vi.fn(),
  uploadTemp: vi.fn(),
}))
vi.mock('@/api/ai', () => ({ aiApi: { chat, pendingList, tools } }))
```

`beforeEach` 里补默认值（照现有 `pendingList` 的写法）：

```ts
  tools.mockReset().mockResolvedValue([])
```

新增用例：

```ts
describe('AgentChat 确认面板', () => {
  it('工具名用 /ai/tools 下发的中文标签渲染', async () => {
    tools.mockResolvedValue([
      { name: 'update_contact', label: '改联系人', description: '', risk: 'write_queue' },
    ])
    pendingList.mockResolvedValue([
      {
        id: 5,
        tool_name: 'update_contact',
        payload: { contact_id: 39, phone: '139' },
        status: 'pending',
        result: null,
        created_at: '2026-10-06T00:00:00Z',
      },
    ])

    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()

    expect(wrapper.get('.pending-item').text()).toContain('改联系人')
  })

  it('标签接口失败时回退工具原名，面板仍可用', async () => {
    tools.mockRejectedValue(new Error('boom'))
    pendingList.mockResolvedValue([
      {
        id: 6,
        tool_name: 'delete_contact',
        payload: { contact_id: 39 },
        status: 'pending',
        result: null,
        created_at: '2026-10-06T00:00:00Z',
      },
    ])

    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()

    expect(wrapper.get('.pending-item').text()).toContain('delete_contact')
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run tests/agentChat.spec.ts
```

预期：新用例失败，`expected ... to contain '改联系人'`（当前渲染的是 `update_contact` 原文）

- [ ] **Step 3: 契约产物加字段**

`frontend/src/api/types.ts`：

```ts
export interface ToolOut {
  name: string
  label: string
  description: string
  risk: 'read' | 'write_queue'
}
```

- [ ] **Step 4: 组件改为消费下发标签**

`frontend/src/components/AgentChat.vue`：删掉 `TOOL_LABELS` 常量（保留 `CONTACT_FIELD_LABELS`、`CONTACT_TIER_LABELS`），新增：

```ts
/** 工具名 → 中文标签：来自 GET /ai/tools（后端单一来源），前端不再维护硬编码映射。 */
const toolLabels = ref<Record<string, string>>({})

/** 拉取标签；失败静默回退原名——标签加载不了不该让整块确认面板不可用。 */
async function loadToolLabels(): Promise<void> {
  try {
    const list = await aiApi.tools()
    toolLabels.value = Object.fromEntries(list.map((tool) => [tool.name, tool.label]))
  } catch {
    toolLabels.value = {}
  }
}

/** 工具中文名（确认面板标题）；未下发的工具回退原名。 */
function labelOf(toolName: string): string {
  return toolLabels.value[toolName] ?? toolName
}
```

把 `onMounted(refreshPending)` 改为：

```ts
onMounted(() => {
  void loadToolLabels()
  void refreshPending()
})
```

模板里把唯一那处引用换掉：

```html
<el-tag size="small" type="warning">{{ labelOf(action.tool_name) }}</el-tag>
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd frontend && npx vitest run tests/agentChat.spec.ts
```

预期：全绿（含原有图片用例）

- [ ] **Step 6: 全量前端测试与构建**

```bash
cd frontend && npm run test && npm run build
```

预期：全绿

- [ ] **Step 7: 提交**

```bash
git add frontend/src/api/types.ts frontend/src/components/AgentChat.vue frontend/tests/agentChat.spec.ts
git commit -m "feat(frontend): 确认面板中文名改由 /ai/tools 下发，删硬编码映射"
```

---

## Task 3: 注册表契约测试

**Files:**
- Create: `backend/tests/test_ai_registry.py`
- Modify: `backend/tests/test_ai_tools.py`（现有 `test_registry_completeness` 与新契约测试重叠，删除它以免两处各断言一份）

**Interfaces:**
- Consumes: Task 1 的 `AiTool.label`；既有的 `pending.EXECUTORS`
- Produces: 契约断言，后续每个阶段的工具都必须满足；`LEGACY_NAMES` 常量供后续阶段收缩

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_ai_registry.py`：

```python
"""工具注册表契约测试：名字唯一、标签齐全、写工具与执行器一一对应。

这组断言的价值不在覆盖行为，而在**拦住静默失败**：
- 缺执行器的写工具，approve() 只会记 ok=False，用户看到的是"提议执行失败"
  而不是"系统缺实现"，排查成本极高；
- 缺 label 的工具，确认面板会显示英文原名；
- 名字不合约定会让模型在 52 个工具里选错。
"""

import pytest

from app.modules.ai import registry
from app.modules.ai.pending import EXECUTORS

pytestmark = pytest.mark.asyncio

# 动词表：新增工具必须以此表之一开头
VERBS = ("list", "get", "create", "update", "delete", "promote", "convert", "mark")

# 历史命名不遵循动词表，冻结在此；新增工具不得再进这个集合。
# Task 7 删除 search_contacts 时，同步把它从本集合移除。
LEGACY_NAMES = {"kinship_of", "semantic_search", "search_contacts"}


def test_tool_names_are_unique():
    """工具名唯一：MCP 注册与 pending_actions.tool_name 都按名字寻址。"""
    names = [tool.name for tool in registry.ALL_TOOLS]
    assert len(names) == len(set(names)), f"重复的工具名：{sorted(names)}"


def test_every_tool_has_label_and_description():
    """每个工具都有中文名与非空描述：前者供确认面板，后者是模型选择工具的唯一依据。"""
    offenders = [
        tool.name
        for tool in registry.ALL_TOOLS
        if not tool.label.strip() or not tool.description.strip()
    ]
    assert offenders == [], f"以下工具缺 label 或 description：{offenders}"


def test_tool_names_follow_verb_entity_convention():
    """新工具名必须是 <动词>_<实体>；历史命名走白名单，不许再扩大。"""
    offenders = [
        tool.name
        for tool in registry.ALL_TOOLS
        if tool.name not in LEGACY_NAMES and tool.name.split("_")[0] not in VERBS
    ]
    assert offenders == [], f"以下工具名不符合 <动词>_<实体>：{offenders}"


def test_write_tools_exactly_match_executors():
    """写工具的集合与执行器表完全相等（双向差集为空）。

    单向断言会漏掉另一半问题：多出的执行器是死代码，
    任何工具改名都会留下它，且不会有任何测试发现。
    """
    write_tools = {tool.name for tool in registry.ALL_TOOLS if tool.risk == "write_queue"}
    assert write_tools - set(EXECUTORS) == set(), "以下写工具没有执行器"
    assert set(EXECUTORS) - write_tools == set(), "以下执行器没有对应的写工具"


def test_read_tools_have_no_executor():
    """读工具直执行，不进确认队列，因此不该有执行器。"""
    read_tools = {tool.name for tool in registry.ALL_TOOLS if tool.risk == "read"}
    assert read_tools & set(EXECUTORS) == set(), "读工具不该有执行器"


def test_every_args_schema_serializes_to_json_schema():
    """每个入参 schema 都能产出 JSON schema：MCP 注册与 agent 绑定的前提。"""
    for tool in registry.ALL_TOOLS:
        schema = tool.args_schema.model_json_schema()
        assert "properties" in schema or schema.get("type") == "object", (
            f"{tool.name} 的 schema 不是对象类型"
        )
```

同时从 `backend/tests/test_ai_tools.py` 删除 `test_registry_completeness`（它的断言已被 `test_ai_registry.py` 覆盖且更完整）。

- [ ] **Step 2: 跑测试确认通过（这一步是纯新增断言，预期直接绿）**

```bash
cd backend && uv run pytest tests/test_ai_registry.py -q
```

预期：6 passed。若有失败，按提示补齐——此时失败都是真实缺陷（例如某个工具确实缺 label）。

- [ ] **Step 3: 故意制造一次失败，确认测试真的会拦**

把 `registry.py` 里 `create_task` 的 `risk` 临时改成 `"read"`，跑：

```bash
cd backend && uv run pytest tests/test_ai_registry.py -q
```

预期：`test_write_tools_exactly_match_executors` 与 `test_read_tools_have_no_executor` 失败。**改回 `"write_queue"`**。

这一步是验证断言不是空的——契约测试最常见的失败模式是写得太松，永远不会红。

- [ ] **Step 4: 确认恢复绿灯**

```bash
cd backend && uv run pytest tests/test_ai_registry.py tests/test_ai_tools.py -q
```

预期：全绿

- [ ] **Step 5: 提交**

```bash
git add backend/tests/test_ai_registry.py backend/tests/test_ai_tools.py
git commit -m "test(ai): 注册表契约测试（标签齐全、写工具与执行器一一对应）"
```

---

## Task 4: `pending_actions.preview` 快照列

**Files:**
- Modify: `backend/app/modules/ai/models.py`（`PendingAction`）
- Modify: `backend/app/modules/ai/pending.py`（`propose`）
- Modify: `backend/app/modules/ai/api.py`（`PendingActionOut`）
- Create: `backend/alembic/versions/<autogenerate>.py`（迁移，文件名由 alembic 生成）
- Modify: `frontend/src/api/types.ts`（`PendingActionOut`）
- Test: `backend/tests/test_ai_pending.py`

**Interfaces:**
- Consumes: 无
- Produces: `PendingAction.preview: dict | None`（JSONB，可空）；
  `propose(db, user, tool_name, payload, reason=None, preview=None) -> PendingAction`；
  `GET /ai/pending` 每项形如 `{id, tool_name, payload, preview, status, result, created_at}`，
  其中 `preview` 为 `null` 或 `{"before": {...}}` 或 `{"summary": str}`

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_ai_pending.py`：

```python
async def test_propose_stores_preview_snapshot(db_session, make_user):
    """preview 与 payload 分离：执行器只消费 payload，preview 仅供确认面板渲染差异。"""
    demo, _ = await make_user(username="demo")

    action = await pending_service.propose(
        db_session,
        demo,
        "update_contact",
        {"contact_id": 39, "phone": "139"},
        preview={"before": {"phone": "138"}},
    )

    assert action.preview == {"before": {"phone": "138"}}
    assert action.payload == {"contact_id": 39, "phone": "139"}


async def test_propose_without_preview_stores_null(db_session, make_user):
    """create 类不填 preview；列可空，面板按 payload 直读渲染。"""
    demo, _ = await make_user(username="demo")

    action = await pending_service.propose(db_session, demo, "create_task", {"title": "买花"})

    assert action.preview is None
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_ai_pending.py -q -k preview
```

预期：`TypeError: propose() got an unexpected keyword argument 'preview'`

- [ ] **Step 3: 加列与参数**

`backend/app/modules/ai/models.py` 的 `PendingAction` 里，在 `payload` 之后加：

```python
    preview: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="确认面板的渲染快照（before/summary），与 payload 分离"
    )
```

`backend/app/modules/ai/pending.py` 的 `propose` 签名与构造：

```python
async def propose(
    db: AsyncSession,
    user: User,
    tool_name: str,
    payload: dict,
    reason: str | None = None,
    preview: dict | None = None,
) -> PendingAction:
    """写入提议入队。

    preview 只服务确认面板的渲染（update 放改动字段的原值、delete 放实体摘要），
    执行器只读 payload——两者分离，避免渲染需求污染落库契约。
    """
```

并在构造 `PendingAction(...)` 时补 `preview=preview`。

`backend/app/modules/ai/api.py` 的 `PendingActionOut` 补：

```python
    preview: dict | None = None
```

`frontend/src/api/types.ts` 的 `PendingActionOut` 补：

```ts
  preview: Record<string, unknown> | null
```

**Step 3b：登记字段级数据模型**（`CLAUDE.md` 要求改动前先登记）。在 `DATA_MODEL.md` 的
`pending_actions` 表下加一行：

```markdown
| preview | JSONB NULL | 确认面板的渲染快照（update 放改动字段原值、delete 放实体摘要）；与 payload 分离，执行器只读 payload |
```

- [ ] **Step 4: 生成迁移**

```bash
cd backend && uv run alembic revision --autogenerate -m "pending_actions 增加 preview 快照列"
```

打开生成的迁移文件核对：`upgrade()` 只应有 `op.add_column("pending_actions", sa.Column("preview", postgresql.JSONB(...), nullable=True))`，`downgrade()` 是对应的 `drop_column`。若 autogenerate 顺带捎上了别的表，删掉那些行——本次只该动这一列。

- [ ] **Step 5: 应用迁移并跑测试**

```bash
cd backend && uv run alembic upgrade head && uv run pytest tests/test_ai_pending.py tests/test_migrations.py -q
```

预期：全绿

- [ ] **Step 6: 全量后端测试**

```bash
cd backend && uv run pytest -q && uv run ruff check .
```

预期：全绿

- [ ] **Step 7: 提交**

```bash
git add backend/app/modules/ai/models.py backend/app/modules/ai/pending.py backend/app/modules/ai/api.py backend/alembic/versions frontend/src/api/types.ts backend/tests/test_ai_pending.py
git commit -m "feat(ai): pending_actions 增加 preview 快照列供确认面板渲染差异"
```

---

## Task 5: 执行器拆进 `executors/` 子包

这是**纯重构，零行为变化**——既有的 `tests/test_ai_pending.py` 是安全网，它必须在这一步前后**一字不改地全绿**。

**Files:**
- Create: `backend/app/modules/ai/executors/__init__.py`、`common.py`、`tasks.py`、`activities.py`、`contacts.py`
- Modify: `backend/app/modules/ai/pending.py`（删掉三个 `_exec_*` 与 `_resolve_contact_id`，改为 import）
- Test: `backend/tests/test_ai_pending.py`（**不修改**，作为回归证据）

**Interfaces:**
- Consumes: 既有 `registry.parse_iso_date` / `registry.resolve_contact_name`
- Produces: `app.modules.ai.executors.EXECUTORS: dict[str, Callable[[AsyncSession, User, dict], Awaitable[dict]]]`；
  `pending.EXECUTORS` 仍可从 `pending` 导入（re-export，Task 3 的契约测试依赖它）

- [ ] **Step 1: 先跑一次基线**

```bash
cd backend && uv run pytest tests/test_ai_pending.py -q
```

预期：全绿。记下通过数，重构后必须一致——这就是"零行为变化"的证据。

- [ ] **Step 2: 建共用助手**

`backend/app/modules/ai/executors/common.py`：

```python
"""执行器共用助手：payload 字段解析（各模块执行器共享，避免各写一份）。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessError
from app.modules.ai.registry import resolve_contact_name
from app.modules.auth.models import User


async def resolve_contact_id(db: AsyncSession, user: User, payload: dict) -> int | None:
    """payload.contact_name → 联系人 id；未提供返回 None，找不到即业务错误。

    执行器拿到的 id 用于落库，所以找不到必须报错而不是静默传 None——
    静默会让"记活动时关联人写错"这种错误无声发生。
    """
    name = payload.get("contact_name")
    if not name:
        return None
    resolved = await resolve_contact_name(db, user, name)
    if resolved is None:
        raise BusinessError(f"没有找到联系人「{name}」，请先在名册中记录")
    return resolved
```

（函数体从 `pending.py::_resolve_contact_id` 原样搬过来，只把名字去掉下划线前缀。）

- [ ] **Step 3: 逐个搬执行器**

把 `pending.py` 里的 `_exec_create_task` 整段搬到 `executors/tasks.py`，改名 `create_task`，并加模块 docstring：

```python
"""待办写工具执行器：确认队列的落库端。"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.executors.common import resolve_contact_id
from app.modules.ai.registry import parse_iso_date
from app.modules.auth.models import User
from app.modules.records import service as records_service
from app.modules.records.schemas import TaskCreate
```

同理 `_exec_create_activity` → `executors/activities.py::create_activity`，
`_exec_create_contact` → `executors/contacts.py::create_contact`。函数体除改名与换 import 外不改动。

- [ ] **Step 4: 汇总表**

`backend/app/modules/ai/executors/__init__.py`：

```python
"""写工具执行器：'工具名 → 落库函数' 的唯一映射（D11 确认队列的落库端）。

按模块分文件，与 registry 的工具分组一一对应。待办/活动/联系人之外的模块
（礼物、资金、关系图、提醒）在本轮后续阶段往这里加文件。
"""

from app.modules.ai.executors.activities import create_activity
from app.modules.ai.executors.contacts import create_contact
from app.modules.ai.executors.tasks import create_task

EXECUTORS = {
    "create_task": create_task,
    "create_activity": create_activity,
    "create_contact": create_contact,
}
```

- [ ] **Step 5: `pending.py` 改为引用**

删掉 `pending.py` 里的三个 `_exec_*`、`_resolve_contact_id` 与原来的 `EXECUTORS` 字面量，改为：

```python
from app.modules.ai.executors import EXECUTORS  # noqa: F401  re-export：调用方与测试从本模块取
```

注意 `approve()` 里的 `EXECUTORS.get(...)` 不用改；`pending.py` 顶部那批现在只被搬走的函数用到的 import（`records_service`、`TaskCreate`、`ActivityCreate`、`datetime` 等）要一并删掉，否则 `ruff check` 会报未使用。

- [ ] **Step 6: 跑回归，确认零行为变化**

```bash
cd backend && uv run pytest tests/test_ai_pending.py tests/test_ai_registry.py -q && uv run ruff check .
```

预期：与 Step 1 的通过数**完全一致**；ruff 干净。

- [ ] **Step 7: 全量后端测试**

```bash
cd backend && uv run pytest -q
```

预期：全绿

- [ ] **Step 8: 提交**

```bash
git add backend/app/modules/ai/executors backend/app/modules/ai/pending.py
git commit -m "refactor(ai): 写工具执行器拆进 executors/ 子包（纯搬迁，无行为变化）"
```

---

## Task 6: 确认面板的差异渲染与多选批量确认

**Files:**
- Modify: `frontend/src/components/AgentChat.vue`（`decide`、`payloadText`、`onMounted` 之后的逻辑区与 `pending-panel` 模板）
- Test: `frontend/tests/agentChat.spec.ts`

**Interfaces:**
- Consumes: Task 4 的 `PendingActionOut.preview`（`null` | `{"before": {...}}` | `{"summary": str}`）；
  Task 2 的 `labelOf(toolName)`
- Produces: 面板支持多选与 `decideMany(approve: boolean)`；
  `previewText(action: PendingActionOut): string`

- [ ] **Step 1: 写失败测试**

追加到 `frontend/tests/agentChat.spec.ts`（沿用文件已有的 `pendingList` mock 与 `MOUNT_OPTIONS`）：

```ts
describe('AgentChat 确认面板渲染与批量', () => {
  const action = (over: Partial<Record<string, unknown>> = {}) => ({
    id: 1,
    tool_name: 'update_contact',
    payload: { contact_id: 39, phone: '139' },
    preview: null,
    status: 'pending',
    result: null,
    created_at: '2026-10-06T00:00:00Z',
    ...over,
  })

  it('update 提议按 preview 显示字段级「原值 → 新值」', async () => {
    pendingList.mockResolvedValue([
      action({ preview: { before: { phone: '138' } } }),
    ])

    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()

    expect(wrapper.get('.pending-item').text()).toContain('phone: 138 → 139')
  })

  it('delete 提议显示将删除的对象', async () => {
    pendingList.mockResolvedValue([
      action({
        tool_name: 'delete_contact',
        payload: { contact_id: 39 },
        preview: { summary: '唐琴（id=39）' },
      }),
    ])

    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()

    expect(wrapper.get('.pending-item').text()).toContain('将删除：唐琴（id=39）')
  })

  it('勾选多条后批量确认：逐条 approve，逐条记结果，不整体回滚', async () => {
    pendingList.mockResolvedValue([action({ id: 1 }), action({ id: 2 })])
    approve
      .mockResolvedValueOnce({ ...action({ id: 1 }), result: { ok: true, message: '已改' } })
      .mockResolvedValueOnce({ ...action({ id: 2 }), result: { ok: false, error: '联系人不存在' } })

    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()

    const boxes = wrapper.findAll('.pending-item input[type="checkbox"]')
    await boxes[0].setValue(true)
    await boxes[1].setValue(true)
    await wrapper.get('[data-test="batch-approve"]').trigger('click')
    await flushPromises()

    expect(approve).toHaveBeenCalledTimes(2)
    expect(approve).toHaveBeenNthCalledWith(1, 1)
    expect(approve).toHaveBeenNthCalledWith(2, 2)
    const text = wrapper.text()
    expect(text).toContain('已改')
    expect(text).toContain('联系人不存在')
  })
})
```

同时把 `approve` 与 `reject` 加进 `vi.hoisted` 与 `vi.mock('@/api/ai', ...)`（现有的 mock 只有 `chat`/`pendingList`/`tools`），并在 `beforeEach` 里 `approve.mockReset()` / `reject.mockReset()`。

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run tests/agentChat.spec.ts -t 确认面板
```

预期：三条全失败（缺 `[data-test="batch-approve"]`、`phone: 138 → 139` 渲染不出来）

- [ ] **Step 3: 实现差异渲染**

在 `AgentChat.vue` 的 `payloadText` 附近新增（`CONTACT_FIELD_LABELS` 已存在，复用）：

```ts
/** 字段中文名：联系人字段有专表，其余实体回退原名（阶段 3+ 再逐模块补）。 */
function fieldLabel(key: string): string {
  return CONTACT_FIELD_LABELS[key] ?? key
}

/** 值的统一展示：数组顿号连接，空值显示破折号。 */
function shown(value: unknown): string {
  if (Array.isArray(value)) return value.join('、')
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

/** 提议正文：update 显示字段级「原值 → 新值」，delete 显示将删除的对象，
 *  create 类按 payload 直读。确认的前提是看懂在确认什么。 */
function previewText(action: PendingActionOut): string {
  const before = action.preview?.before as Record<string, unknown> | undefined
  if (before) {
    return Object.entries(before)
      .map(([key, oldValue]) => `${fieldLabel(key)}: ${shown(oldValue)} → ${shown(action.payload[key])}`)
      .join(' · ')
  }
  if (action.preview?.summary) return `将删除：${String(action.preview.summary)}`
  return payloadText(action)
}
```

- [ ] **Step 4: 实现多选与批量**

新增状态与函数：

```ts
/** 已勾选待处理的提议 id（数组由组件自己维护，不依赖 checkbox 的 group 语义）。 */
const selectedIds = ref<number[]>([])
const batchRunning = ref(false)

const allSelected = computed(
  () => pendingActions.value.length > 0 && selectedIds.value.length === pendingActions.value.length,
)

/** 勾选/取消单条提议。 */
function toggleSelect(id: number, checked: boolean): void {
  selectedIds.value = checked
    ? [...selectedIds.value, id]
    : selectedIds.value.filter((item) => item !== id)
}

/** 全选/取消全选当前面板里的提议。 */
function toggleSelectAll(checked: boolean): void {
  selectedIds.value = checked ? pendingActions.value.map((action) => action.id) : []
}

/** 单条确认结果文案（单条与批量共用，避免两处措辞漂移）。 */
function outcomeOf(result: PendingActionOut): string {
  return result.result?.ok
    ? `✅ ${result.result.message}`
    : `⚠ 执行失败：${result.result?.error ?? '未知原因'}`
}
```

把现有 `decide` 里那段三目改成调用 `outcomeOf(result)`。

新增 `decideMany`：

```ts
/** 批量确认/驳回：逐条调用既有端点，每条独立事务。
 *
 * 刻意不做整体回滚——各条提议之间没有依赖，已成功的那条不该因为
 * 后面一条失败而被撤销；逐条把结果写回对话，用户能看到哪几条成了。
 */
async function decideMany(approve: boolean): Promise<void> {
  const ids = [...selectedIds.value]
  if (!ids.length || batchRunning.value) return
  batchRunning.value = true
  const outcomes: string[] = []
  try {
    for (const id of ids) {
      try {
        const result = approve ? await aiApi.approve(id) : await aiApi.reject(id)
        outcomes.push(approve ? `#${id} ${outcomeOf(result)}` : `#${id} 已拒绝`)
      } catch (error) {
        outcomes.push(`#${id} ⚠ ${error instanceof ApiError ? error.message : '操作失败'}`)
      }
    }
  } finally {
    batchRunning.value = false
    selectedIds.value = []
  }
  messages.value.push({ role: 'assistant', content: outcomes.join('\n'), tools: [] })
  await refreshPending()
  await scrollToBottom()
}
```

`refreshPending()` 之后清空勾选（列表已重取，旧 id 可能不再存在）：在 `refreshPending` 里补 `selectedIds.value = []` 更稳——**选这个位置**，这样单条确认后也会清掉。

模板：`pending-head` 里加全选与两个批量按钮，`pending-item` 的标题行加勾选框、正文换成 `previewText(action)`：

```html
    <div v-if="showPending" class="pending-panel">
      <div class="pending-head">
        <span>待确认的写入提议</span>
        <el-checkbox
          v-if="pendingActions.length"
          :model-value="allSelected"
          :indeterminate="selectedIds.length > 0 && !allSelected"
          @change="toggleSelectAll"
        >全选</el-checkbox>
        <el-button
          type="primary" size="small"
          data-test="batch-approve"
          :loading="batchRunning"
          :disabled="!selectedIds.length"
          @click="decideMany(true)"
        >确认选中</el-button>
        <el-button
          text size="small"
          data-test="batch-reject"
          :disabled="!selectedIds.length"
          @click="decideMany(false)"
        >驳回选中</el-button>
        <el-button text @click="showPending = false">收起</el-button>
      </div>
      <div v-for="action in pendingActions" :key="action.id" class="pending-item">
        <div class="pending-title">
          <el-checkbox
            :model-value="selectedIds.includes(action.id)"
            @change="(checked: boolean) => toggleSelect(action.id, checked)"
          />
          <el-tag size="small" type="warning">{{ labelOf(action.tool_name) }}</el-tag>
          <span>{{ previewText(action) }}</span>
        </div>
        <div class="pending-actions">
          <el-button type="primary" @click="decide(action, true)">确认执行</el-button>
          <el-button text @click="decide(action, false)">拒绝</el-button>
        </div>
      </div>
      <p v-if="!pendingActions.length" class="pending-empty">没有待确认的提议</p>
    </div>
```

样式只消费 `design/tokens.ts`：`.pending-head` 需要 `display: flex; align-items: center; gap: 8px;`，`flex: 1` 留给标题文字把按钮推到右侧。

- [ ] **Step 5: 跑测试确认通过**

```bash
cd frontend && npx vitest run tests/agentChat.spec.ts
```

预期：全绿

- [ ] **Step 6: 全量前端测试与构建**

```bash
cd frontend && npm run test && npm run build
```

预期：全绿

- [ ] **Step 7: 浏览器人工核验**

```bash
./dev.sh
```

在 http://localhost:5180 登录 `demo` / `demo12345`，进助理页，让助理记一件事生成提议，确认面板应能看到：勾选框、全选、「确认选中 / 驳回选中」按钮；两条以上时勾选两条点「确认选中」，对话里应出现两行结果。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/components/AgentChat.vue frontend/tests/agentChat.spec.ts
git commit -m "feat(frontend): 确认面板显示字段级差异，支持多选批量确认/驳回"
```

---

## Task 7: contacts 读工具，删除 `search_contacts`

**Files:**
- Modify: `backend/app/modules/ai/registry.py`（删 `SearchContactsArgs` 与 `_run_search_contacts` 及注册项；加 `ListContactsArgs`、`GetContactArgs` 与两个处理函数）
- Modify: `backend/agent/runner.py`（`SYSTEM_PROMPT` 里的 `search_contacts` 引用改为 `list_contacts`）
- Modify: `backend/tests/test_ai_registry.py`（`LEGACY_NAMES` 移除 `search_contacts`）
- Test: `backend/tests/test_ai_tools.py`

**Interfaces:**
- Consumes: `contacts_service.list_contacts(db, user, *, tier, search, activity)`、
  `contacts_service.get_contact(db, user, contact_id) -> ContactDetailOut`（含 `dates`）
- Produces: 工具 `list_contacts(tier?, search?, activity?)`、`get_contact(contact_id)`；
  `search_contacts` **不再存在**（破坏性变更，spec §3.5）

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_ai_tools.py`（顶部 import 补 `create_date_for`、`from app.core.errors import NotFoundError` 不需要——读工具把不可见转成文案而非抛错）：

```python
async def test_list_contacts_returns_ids_and_distinguishing_fields(db_session, make_user):
    """每条都带 id 与可区分字段：多命中时模型要能复述候选给用户确认（spec §3.4）。"""
    demo, _ = await make_user(username="demo")
    await create_contact_for(demo, name="唐琴", organization="极星科技")
    await create_contact_for(demo, name="唐琴", organization="另一家")

    text = await _run_tool(db_session, demo, "list_contacts", search="唐琴")

    assert text.count("id=") == 2
    assert "极星科技" in text and "另一家" in text


async def test_get_contact_returns_full_fields_and_dates(db_session, make_user):
    """get_contact 是改之前的回读入口：字段与重要日期一次给全。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴", phone="13800000000")
    await create_date_for(
        demo, contact.id, type="birthday", calendar="lunar", lunar_month=9, lunar_day=24
    )

    text = await _run_tool(db_session, demo, "get_contact", contact_id=contact.id)

    assert "唐琴" in text
    assert "13800000000" in text
    assert "农历" in text


async def test_get_contact_of_unreadable_contact_reports_not_found(db_session, make_user):
    """别人的私密联系人不可读：报"没有找到"，不泄露它是否存在。"""
    owner, _ = await make_user(username="owner")
    other, _ = await make_user(username="other", family_id=owner.family_id)
    secret = await create_contact_for(owner, name="私密人", visibility="private")

    text = await _run_tool(db_session, other, "get_contact", contact_id=secret.id)

    assert "没有找到" in text
    assert "私密人" not in text


async def test_search_contacts_is_gone(db_session, make_user):
    """search_contacts 已合并进 list_contacts（spec §3.5）：按名寻址的入口不应存在。"""
    assert get_tool("search_contacts") is None
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_ai_tools.py -q -k "list_contacts or get_contact or search_contacts_is_gone"
```

预期：前两条 `工具 list_contacts 未注册`，最后一条 `assert AiTool(...) is None` 失败

- [ ] **Step 3: 加两个读工具**

`registry.py` 里新增入参 schema：

```python
class ListContactsArgs(BaseModel):
    """名册列表入参：不传任何条件即全量（受调用者可读范围约束）。"""

    tier: Literal["direct", "edge"] | None = Field(default=None, description="层级过滤")
    search: str | None = Field(default=None, description="姓名/昵称/单位关键字")
    activity: Literal["recent_30d", "stale_180d"] | None = Field(
        default=None, description="recent_30d=近 30 天联系过；stale_180d=超半年未联系"
    )


class GetContactArgs(BaseModel):
    """读单人完整资料入参（含重要日期）。"""

    contact_id: int
```

处理函数：

```python
async def _run_list_contacts(db: AsyncSession, user, args: ListContactsArgs) -> str:
    """名册列表：每条给 id + 展示名 + 可区分字段，供模型复述候选给用户确认。"""
    contacts = await contacts_service.list_contacts(
        db, user, tier=args.tier, search=args.search, activity=args.activity
    )
    if not contacts:
        return "没有符合条件的联系人"
    lines = [
        f"- {c.display_name}（id={c.id}，{'边缘' if c.tier == 'edge' else '直接'}联系人"
        f"{'，单位：' + c.organization if c.organization else ''}，{c.owner_display_name} 记录）"
        for c in contacts
    ]
    return f"共 {len(contacts)} 位：\n" + "\n".join(lines)


async def _run_get_contact(db: AsyncSession, user, args: GetContactArgs) -> str:
    """读单人完整资料 + 重要日期：改之前的回读入口（看得到现状才谈得上改）。"""
    try:
        detail = await contacts_service.get_contact(db, user, args.contact_id)
    except NotFoundError:
        # 不可读与不存在给同一句话，不泄露存在性（判权口径见 permission.py）
        return f"没有找到 id={args.contact_id} 的联系人"
    fields = [
        ("姓名", detail.name),
        ("昵称", detail.nickname),
        ("单位", detail.organization),
        ("电话", detail.phone),
        ("微信", detail.wechat),
        ("QQ", detail.qq),
        ("邮箱", detail.email),
        ("毕业院校", detail.school_name),
        ("现居地", detail.current_address),
        ("家庭地址", detail.family_address),
        ("兴趣爱好", detail.hobbies),
        ("所在地", detail.location),
        ("备注", detail.bio),
        ("层级", "边缘" if detail.tier == "edge" else "直接"),
    ]
    lines = [f"{label}：{value}" for label, value in fields if value]
    if detail.dates:
        lines.append("重要日期：")
        for item in detail.dates:
            when = (
                item.date_solar.isoformat()
                if item.date_solar
                else f"农历 {item.lunar_month} 月 {item.lunar_day} 日"
            )
            lead = "、".join(str(day) for day in item.reminder_lead_days)
            lines.append(f"  - id={item.id} {item.type} {when}（提前 {lead} 天提醒）")
    return f"联系人 id={detail.id} 的资料：\n" + "\n".join(lines)
```

顶部 import 补 `from app.core.errors import NotFoundError`。

- [ ] **Step 4: 换注册项**

从 `ALL_TOOLS` 里删掉整个 `search_contacts` 条目与它的 `SearchContactsArgs` / `_run_search_contacts`，加入：

```python
    AiTool(
        name="list_contacts",
        label="查名册",
        description=(
            "列出可读联系人（可按层级/关键字/联系活跃度过滤），每条带 id；"
            "找人、看名册、以及任何后续要按 id 操作的场景都先用它拿 id"
        ),
        risk="read",
        args_schema=ListContactsArgs,
        run=_run_list_contacts,
    ),
    AiTool(
        name="get_contact",
        label="读联系人资料",
        description=(
            "按 id 读某位联系人的完整资料与重要日期；**改任何联系人字段之前必须先用它回读现状**"
        ),
        risk="read",
        args_schema=GetContactArgs,
        run=_run_get_contact,
    ),
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd backend && uv run pytest tests/test_ai_tools.py tests/test_ai_registry.py -q
```

预期：全绿（`test_ai_registry.py` 会因 `LEGACY_NAMES` 仍含 `search_contacts` 而**继续绿**——白名单多一个不存在的名字不报错，下一步清掉）

- [ ] **Step 6: 清掉白名单里的旧名**

`backend/tests/test_ai_registry.py`：

```python
LEGACY_NAMES = {"kinship_of", "semantic_search"}
```

- [ ] **Step 7: 改提示词里的引用**

`backend/agent/runner.py` 的 `SYSTEM_PROMPT`，把两处 `search_contacts` 改为 `list_contacts`（第 2 条的"找某个人的信息"与第 5 条的"先用 … 查同名"）。本步只做改名，改/删纪律在 Task 10 一并写。

- [ ] **Step 8: 跑全量后端测试**

```bash
cd backend && uv run pytest -q && uv run ruff check .
```

预期：全绿

- [ ] **Step 9: 提交**

```bash
git add backend/app/modules/ai/registry.py backend/agent/runner.py backend/tests/test_ai_registry.py backend/tests/test_ai_tools.py
git commit -m "feat(ai): 加 list_contacts/get_contact，删 search_contacts（合并进 list_contacts）"
```

---

## Task 8: contacts 写工具（改 / 归档 / 升级）

**Files:**
- Modify: `backend/app/modules/ai/registry.py`（三个 schema + 三个处理函数 + 注册项）
- Modify: `backend/app/modules/ai/executors/contacts.py`（三个执行器）
- Modify: `backend/app/modules/ai/executors/__init__.py`（汇总表加三条）
- Test: `backend/tests/test_ai_tools.py`、`backend/tests/test_ai_pending.py`

**Interfaces:**
- Consumes: `contacts_service.update_contact(db, user, contact_id, data) -> ContactDetailOut`、
  `archive_contact(db, user, contact_id) -> None`、`promote_contact(db, user, contact_id) -> ContactDetailOut`、
  `ContactUpdate`（contacts/schemas.py）
- Produces: 工具 `update_contact` / `delete_contact` / `promote_contact`（均 `write_queue`）；
  执行器同名函数；`payload["contact_id"]` 是这三个工具的寻址键

- [ ] **Step 1: 写失败测试（工具侧）**

追加到 `backend/tests/test_ai_tools.py`：

```python
async def test_update_contact_proposal_carries_before_snapshot(db_session, make_user):
    """改联系人提议：payload 只带要改的字段，preview 带它们的原值供面板显示差异。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴", phone="138")

    text = await _run_tool(db_session, demo, "update_contact", contact_id=contact.id, phone="139")

    assert "已生成修改联系人提议" in text
    action = (await pending_service.list_pending(db_session, demo))[0]
    assert action.payload == {"contact_id": contact.id, "phone": "139"}
    assert action.preview == {"before": {"phone": "138"}}


async def test_update_contact_rejects_unknown_field(db_session, make_user):
    """payload 混入不该改的字段（属主/家庭）应被 schema 挡下，不能越权改属主。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴")

    with pytest.raises(ValidationError):
        await _run_tool(
            db_session, demo, "update_contact", contact_id=contact.id, owner_user_id=999
        )


async def test_update_contact_rejects_empty_change_set(db_session, make_user):
    """空改动的"成功"是假的：模型会以为改好了，用户什么也没看到。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴")

    with pytest.raises(ValidationError):
        await _run_tool(db_session, demo, "update_contact", contact_id=contact.id)


async def test_update_contact_of_unreadable_contact_is_rejected(db_session, make_user):
    """别人的私密联系人不可改：提议阶段就报错，不泄露它是否存在。"""
    owner, _ = await make_user(username="owner")
    other, _ = await make_user(username="other", family_id=owner.family_id)
    secret = await create_contact_for(owner, name="私密人", visibility="private")

    with pytest.raises(NotFoundError):
        await _run_tool(db_session, other, "update_contact", contact_id=secret.id, phone="139")


async def test_delete_contact_proposal_carries_summary(db_session, make_user):
    """归档提议的 preview 带实体摘要，确认面板才能显示"将删除：谁"。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴")

    await _run_tool(db_session, demo, "delete_contact", contact_id=contact.id)

    action = (await pending_service.list_pending(db_session, demo))[0]
    assert action.preview == {"summary": f"唐琴（id={contact.id}）"}
```

`test_ai_tools.py` 顶部补 import：`import pytest`、`from pydantic import ValidationError`、
`from app.core.errors import NotFoundError`、
`from app.modules.ai import pending as pending_service`（若无则加）。

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_ai_tools.py -q -k "update_contact or delete_contact"
```

预期：`工具 update_contact 未注册`

- [ ] **Step 3: 写三个 schema**

`registry.py`，注意 `extra="forbid"` 与"至少一个字段"两条约束：

```python
class UpdateContactArgs(BaseModel):
    """改联系人入参（PATCH 语义：只提交要改的字段）。

    刻意不含 id / owner_user_id / family_id / tier：
    前三个决定权限归属，改它们等于越权；层级有专门的 promote_contact 工具，
    两条路会让"谁把人升成直接联系人"失去单一入口。
    """

    model_config = ConfigDict(extra="forbid")

    contact_id: int
    name: str | None = Field(default=None, max_length=100)
    nickname: str | None = Field(default=None, max_length=100)
    gender: Literal["male", "female", "other", "unknown"] | None = None
    organization: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    qq: str | None = Field(default=None, max_length=30)
    wechat: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=120)
    school_name: str | None = Field(default=None, max_length=100)
    current_address: str | None = Field(default=None, max_length=200)
    family_address: str | None = Field(default=None, max_length=200)
    hobbies: str | None = None
    location: str | None = Field(default=None, max_length=200)
    bio: str | None = None

    @model_validator(mode="after")
    def validate_at_least_one_change(self) -> "UpdateContactArgs":
        """至少要改一个字段：空改动的"成功"是假的。"""
        if not self.model_dump(exclude={"contact_id"}, exclude_none=True):
            raise ValueError("至少要指定一个要修改的字段")
        return self


class ContactIdArgs(BaseModel):
    """只需联系人 id 的写工具入参（归档 / 升级共用）。"""

    contact_id: int
```

- [ ] **Step 4: 写三个处理函数**

```python
async def _run_queue_update_contact(db: AsyncSession, user, args: UpdateContactArgs) -> str:
    """改联系人提议入队：回读现状拿原值，preview 供面板显示字段级差异。"""
    from app.modules.ai import pending as pending_service

    detail = await contacts_service.get_contact(db, user, args.contact_id)
    changes = args.model_dump(exclude={"contact_id"}, exclude_none=True)
    before = {key: getattr(detail, key, None) for key in changes}
    action = await pending_service.propose(
        db,
        user,
        "update_contact",
        {"contact_id": args.contact_id, **changes},
        preview={"before": before},
    )
    summary = "、".join(f"{key} → {value}" for key, value in changes.items())
    return (
        f"已生成修改联系人提议（编号 {action.id}，待确认）：{detail.display_name}"
        f"（id={detail.id}）的 {summary}。需要用户在界面确认后才会生效。"
    )


async def _run_queue_delete_contact(db: AsyncSession, user, args: ContactIdArgs) -> str:
    """归档联系人提议入队：preview 带实体摘要，面板显示"将删除：谁"。"""
    from app.modules.ai import pending as pending_service

    detail = await contacts_service.get_contact(db, user, args.contact_id)
    action = await pending_service.propose(
        db,
        user,
        "delete_contact",
        {"contact_id": args.contact_id},
        preview={"summary": f"{detail.display_name}（id={detail.id}）"},
    )
    return (
        f"已生成归档联系人提议（编号 {action.id}，待确认）：{detail.display_name}"
        f"（id={detail.id}）。归档是软删，可在名册中恢复；需要用户在界面确认后才会执行。"
    )


async def _run_queue_promote_contact(db: AsyncSession, user, args: ContactIdArgs) -> str:
    """边缘 → 直接 升级提议入队。"""
    from app.modules.ai import pending as pending_service

    detail = await contacts_service.get_contact(db, user, args.contact_id)
    action = await pending_service.propose(
        db,
        user,
        "promote_contact",
        {"contact_id": args.contact_id},
        preview={"summary": f"{detail.display_name}（id={detail.id}）升级为直接联系人"},
    )
    return (
        f"已生成升级联系人提议（编号 {action.id}，待确认）：{detail.display_name}"
        f"（id={detail.id}）。需要用户在界面确认后才会生效。"
    )
```

- [ ] **Step 5: 写三个执行器**

`backend/app/modules/ai/executors/contacts.py` 追加（顶部 import 补 `ContactUpdate`）：

```python
async def update_contact(db: AsyncSession, user: User, payload: dict) -> dict:
    """改联系人：走 contacts service 的 PATCH 语义（只改提交的字段）。"""
    data = ContactUpdate(**{key: value for key, value in payload.items() if key != "contact_id"})
    contact = await contacts_service.update_contact(db, user, payload["contact_id"], data)
    return {"ok": True, "message": f"已更新 {contact.display_name}（id={contact.id}）"}


async def delete_contact(db: AsyncSession, user: User, payload: dict) -> dict:
    """归档联系人（软删，仅所有者）：与 HTTP 的 DELETE 端点同一个 service 函数。"""
    await contacts_service.archive_contact(db, user, payload["contact_id"])
    return {"ok": True, "message": "已归档该联系人"}


async def promote_contact(db: AsyncSession, user: User, payload: dict) -> dict:
    """边缘联系人升级为直接联系人：升级保留全部数据（与其他入口同一个函数）。"""
    contact = await contacts_service.promote_contact(db, user, payload["contact_id"])
    return {"ok": True, "message": f"{contact.display_name} 已升级为直接联系人"}
```

`executors/__init__.py` 的 `EXECUTORS` 加三条：

```python
    "update_contact": update_contact,
    "delete_contact": delete_contact,
    "promote_contact": promote_contact,
```

（import 行相应改为 `from app.modules.ai.executors.contacts import create_contact, delete_contact, promote_contact, update_contact`。）

- [ ] **Step 6: 注册三个工具**

`registry.py` 的 `ALL_TOOLS` 末尾追加：

```python
    AiTool(
        name="update_contact",
        label="改联系人",
        description=(
            "修改已有联系人的字段（只提交要改的项，需用户确认后生效）；"
            "调它之前必须先用 get_contact 回读现状，禁止凭空改写"
        ),
        risk="write_queue",
        args_schema=UpdateContactArgs,
        run=_run_queue_update_contact,
    ),
    AiTool(
        name="delete_contact",
        label="归档联系人",
        description="归档（软删）一位联系人，仅所有者可归档（需用户确认后生效）",
        risk="write_queue",
        args_schema=ContactIdArgs,
        run=_run_queue_delete_contact,
    ),
    AiTool(
        name="promote_contact",
        label="升级为直接联系人",
        description="把边缘联系人升级为直接联系人，数据全部保留（需用户确认后生效）",
        risk="write_queue",
        args_schema=ContactIdArgs,
        run=_run_queue_promote_contact,
    ),
```

- [ ] **Step 7: 跑测试确认通过**

```bash
cd backend && uv run pytest tests/test_ai_tools.py tests/test_ai_registry.py -q
```

预期：全绿（契约测试会确认三个新写工具都有执行器）

- [ ] **Step 8: 写执行器侧测试**

追加到 `backend/tests/test_ai_pending.py`：

```python
async def test_approve_update_contact_changes_only_submitted_fields(db_session, make_user):
    """确认改联系人：只改提交字段，其余字段原样保留。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴", phone="138", organization="极星科技")
    action = await pending_service.propose(
        db_session, demo, "update_contact", {"contact_id": contact.id, "phone": "139"}
    )

    await pending_service.approve(db_session, demo, action.id)

    from app.modules.contacts import service as contacts_service

    detail = await contacts_service.get_contact(db_session, demo, contact.id)
    assert detail.phone == "139"
    assert detail.organization == "极星科技", "未提交的字段不该被清空"


async def test_approve_update_on_missing_contact_records_failure(db_session, make_user):
    """提议引用的联系人已不存在：记 ok=False 让人看见失败，不 500 卡在 pending。"""
    demo, _ = await make_user(username="demo")
    action = await pending_service.propose(
        db_session, demo, "update_contact", {"contact_id": 999999, "phone": "139"}
    )

    result = await pending_service.approve(db_session, demo, action.id)

    assert result.status == "executed"
    assert result.result["ok"] is False


async def test_approve_delete_contact_archives_it(db_session, make_user):
    """确认归档：联系人从名册消失（软删），不物理删除。"""
    from app.modules.contacts import service as contacts_service

    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴")
    action = await pending_service.propose(
        db_session, demo, "delete_contact", {"contact_id": contact.id}
    )

    result = await pending_service.approve(db_session, demo, action.id)

    assert result.result["ok"] is True
    with pytest.raises(NotFoundError):
        await contacts_service.get_contact(db_session, demo, contact.id)
```

`test_ai_pending.py` 顶部补 `from app.core.errors import NotFoundError`。

- [ ] **Step 9: 跑测试确认通过**

```bash
cd backend && uv run pytest tests/test_ai_pending.py tests/test_ai_tools.py tests/test_ai_registry.py -q
```

预期：全绿

- [ ] **Step 10: 全量后端测试与 lint**

```bash
cd backend && uv run pytest -q && uv run ruff check .
```

预期：全绿

- [ ] **Step 11: 提交**

```bash
git add backend/app/modules/ai/registry.py backend/app/modules/ai/executors backend/tests/test_ai_tools.py backend/tests/test_ai_pending.py
git commit -m "feat(ai): contacts 写工具（改/归档/升级）+ 执行器，含 preview 快照"
```

---

## Task 9: 重要日期三件套

**Files:**
- Modify: `backend/app/modules/ai/registry.py`（三个 schema + 三个处理函数 + 注册项）
- Modify: `backend/app/modules/ai/executors/contacts.py`（三个执行器）
- Modify: `backend/app/modules/ai/executors/__init__.py`
- Test: `backend/tests/test_ai_tools.py`、`backend/tests/test_ai_pending.py`

**Interfaces:**
- Consumes: `contacts_service.create_date(db, user, contact_id, data) -> ContactDetailOut`、
  `update_date(db, user, contact_id, date_id, data) -> ContactDetailOut`、
  `delete_date(db, user, contact_id, date_id) -> None`、
  `ImportantDateCreate` / `ImportantDateUpdate`（contacts/schemas.py）、
  `registry.parse_iso_date(value, field_name) -> date`
- Produces: 工具 `add_important_date` / `update_important_date` / `delete_important_date`（均 `write_queue`）

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_ai_tools.py`：

```python
async def test_add_lunar_important_date_proposal(db_session, make_user):
    """农历生日提议：公历日期字符串转 date 后入队，农历字段原样带过去。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴")

    text = await _run_tool(
        db_session,
        demo,
        "add_important_date",
        contact_id=contact.id,
        calendar="lunar",
        lunar_month=9,
        lunar_day=24,
    )

    assert "已生成加重要日期提议" in text
    action = (await pending_service.list_pending(db_session, demo))[0]
    assert action.payload["lunar_month"] == 9
    assert action.payload["contact_id"] == contact.id


async def test_add_solar_date_rejects_bad_date_string(db_session, make_user):
    """公历日期字符串非法：提议阶段就报错，让模型当场改，而不是等到用户确认才失败。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴")

    with pytest.raises(ValidationError):
        await _run_tool(
            db_session,
            demo,
            "add_important_date",
            contact_id=contact.id,
            calendar="solar",
            date_solar="2026-13-45",
        )


async def test_delete_important_date_proposal_carries_summary(db_session, make_user):
    """删日期提议：preview 摘要写清是谁的哪条日期，面板才显示得明白。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴")
    date_row = await create_date_for(demo, contact.id, type="birthday", calendar="solar")

    await _run_tool(
        db_session, demo, "delete_important_date", contact_id=contact.id, date_id=date_row.id
    )

    action = (await pending_service.list_pending(db_session, demo))[0]
    assert "唐琴" in action.preview["summary"]
    assert "birthday" in action.preview["summary"]
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_ai_tools.py -q -k important_date
```

预期：`工具 add_important_date 未注册`

- [ ] **Step 3: 写三个 schema**

```python
class AddImportantDateArgs(BaseModel):
    """加重要日期入参：calendar=solar 必填 date_solar；calendar=lunar 必填合法农历月日。"""

    model_config = ConfigDict(extra="forbid")

    contact_id: int
    type: str = Field(default="birthday", description="birthday/anniversary/other")
    title: str | None = Field(default=None, max_length=100)
    calendar: Literal["solar", "lunar"]
    date_solar: str | None = Field(default=None, description="公历日期 YYYY-MM-DD（calendar=solar）")
    lunar_month: int | None = Field(default=None, ge=1, le=12)
    lunar_day: int | None = Field(default=None, ge=1, le=30)
    lunar_is_leap: bool = False
    yearly: bool = True
    reminder_lead_days: list[int] = Field(default_factory=lambda: [7, 1])


class UpdateImportantDateArgs(BaseModel):
    """改重要日期入参：只提交要改的项。"""

    model_config = ConfigDict(extra="forbid")

    contact_id: int
    date_id: int
    title: str | None = Field(default=None, max_length=100)
    calendar: Literal["solar", "lunar"] | None = None
    date_solar: str | None = Field(default=None, description="公历日期 YYYY-MM-DD")
    lunar_month: int | None = Field(default=None, ge=1, le=12)
    lunar_day: int | None = Field(default=None, ge=1, le=30)
    lunar_is_leap: bool | None = None
    yearly: bool | None = None
    reminder_lead_days: list[int] | None = None

    @model_validator(mode="after")
    def validate_at_least_one_change(self) -> "UpdateImportantDateArgs":
        """至少要改一个字段（contact_id/date_id 是寻址，不算改动）。"""
        if not self.model_dump(exclude={"contact_id", "date_id"}, exclude_none=True):
            raise ValueError("至少要指定一个要修改的字段")
        return self


class DateIdArgs(BaseModel):
    """删重要日期入参。"""

    model_config = ConfigDict(extra="forbid")

    contact_id: int
    date_id: int
```

- [ ] **Step 4: 写三个处理函数**

```python
async def _run_queue_add_important_date(db: AsyncSession, user, args: AddImportantDateArgs) -> str:
    """加重要日期提议入队：提议阶段就用原 schema 校验，模型能当场改错。"""
    from app.modules.ai import pending as pending_service
    from app.modules.contacts.schemas import ImportantDateCreate

    data = ImportantDateCreate(
        type=args.type,
        title=args.title,
        calendar=args.calendar,
        date_solar=parse_iso_date(args.date_solar, "date_solar") if args.date_solar else None,
        lunar_month=args.lunar_month,
        lunar_day=args.lunar_day,
        lunar_is_leap=args.lunar_is_leap,
        yearly=args.yearly,
        reminder_lead_days=args.reminder_lead_days,
    )
    payload = {
        "contact_id": args.contact_id,
        **data.model_dump(mode="json", exclude_none=True),
    }
    action = await pending_service.propose(db, user, "add_important_date", payload)
    when = data.date_solar.isoformat() if data.date_solar else f"农历 {data.lunar_month} 月 {data.lunar_day} 日"
    return (
        f"已生成加重要日期提议（编号 {action.id}，待确认）：{when}。"
        f"需要用户在界面确认后才会生效。"
    )


async def _run_queue_update_important_date(
    db: AsyncSession, user, args: UpdateImportantDateArgs
) -> str:
    """改重要日期提议入队：preview 取该日期的字段原值供面板显示差异。"""
    from app.modules.ai import pending as pending_service

    detail = await contacts_service.get_contact(db, user, args.contact_id)
    current = next((item for item in detail.dates if item.id == args.date_id), None)
    if current is None:
        return f"没有找到 id={args.date_id} 的重要日期（或它不属于这位联系人）"
    changes = args.model_dump(exclude={"contact_id", "date_id"}, exclude_none=True)
    if "date_solar" in changes:
        changes["date_solar"] = parse_iso_date(changes["date_solar"], "date_solar").isoformat()
    before = {key: getattr(current, key) for key in changes}
    action = await pending_service.propose(
        db,
        user,
        "update_important_date",
        {"contact_id": args.contact_id, "date_id": args.date_id, **changes},
        preview={"before": before},
    )
    summary = "、".join(f"{key} → {value}" for key, value in changes.items())
    return (
        f"已生成修改重要日期提议（编号 {action.id}，待确认）：{detail.display_name} 的 "
        f"{summary}。需要用户在界面确认后才会生效。"
    )


async def _run_queue_delete_important_date(db: AsyncSession, user, args: DateIdArgs) -> str:
    """删重要日期提议入队：preview 摘要写清是谁的哪条日期。"""
    from app.modules.ai import pending as pending_service

    detail = await contacts_service.get_contact(db, user, args.contact_id)
    current = next((item for item in detail.dates if item.id == args.date_id), None)
    if current is None:
        return f"没有找到 id={args.date_id} 的重要日期（或它不属于这位联系人）"
    when = current.date_solar.isoformat() if current.date_solar else f"农历 {current.lunar_month} 月 {current.lunar_day} 日"
    action = await pending_service.propose(
        db,
        user,
        "delete_important_date",
        {"contact_id": args.contact_id, "date_id": args.date_id},
        preview={"summary": f"{detail.display_name} 的 {current.type} {when}"},
    )
    return f"已生成删除重要日期提议（编号 {action.id}，待确认）。需要用户在界面确认后才会执行。"
```

- [ ] **Step 5: 写三个执行器**

`executors/contacts.py` 追加（import 补 `ImportantDateCreate`、`ImportantDateUpdate`）：

```python
async def add_important_date(db: AsyncSession, user: User, payload: dict) -> dict:
    """加重要日期：走 contacts service，与原端点同一套历法校验。"""
    body = {key: value for key, value in payload.items() if key != "contact_id"}
    data = ImportantDateCreate(**body)
    contact = await contacts_service.create_date(db, user, payload["contact_id"], data)
    return {"ok": True, "message": f"已给 {contact.display_name} 加上重要日期"}


async def update_important_date(db: AsyncSession, user: User, payload: dict) -> dict:
    """改重要日期：只改提交的字段。"""
    body = {key: value for key, value in payload.items() if key not in ("contact_id", "date_id")}
    data = ImportantDateUpdate(**body)
    contact = await contacts_service.update_date(
        db, user, payload["contact_id"], payload["date_id"], data
    )
    return {"ok": True, "message": f"已更新 {contact.display_name} 的重要日期"}


async def delete_important_date(db: AsyncSession, user: User, payload: dict) -> dict:
    """删重要日期。"""
    await contacts_service.delete_date(db, user, payload["contact_id"], payload["date_id"])
    return {"ok": True, "message": "已删除该重要日期"}
```

`executors/__init__.py` 汇总表加三条并补 import。

- [ ] **Step 6: 注册三个工具**

```python
    AiTool(
        name="add_important_date",
        label="加重要日期",
        description=(
            "给某位联系人加一条重要日期（生日/纪念日），支持公历与农历"
            "（需用户确认后生效）"
        ),
        risk="write_queue",
        args_schema=AddImportantDateArgs,
        run=_run_queue_add_important_date,
    ),
    AiTool(
        name="update_important_date",
        label="改重要日期",
        description="修改某位联系人的一条重要日期（需用户确认后生效）",
        risk="write_queue",
        args_schema=UpdateImportantDateArgs,
        run=_run_queue_update_important_date,
    ),
    AiTool(
        name="delete_important_date",
        label="删重要日期",
        description="删除某位联系人的一条重要日期（需用户确认后生效）",
        risk="write_queue",
        args_schema=DateIdArgs,
        run=_run_queue_delete_important_date,
    ),
```

- [ ] **Step 7: 跑测试确认通过**

```bash
cd backend && uv run pytest tests/test_ai_tools.py tests/test_ai_registry.py -q
```

预期：全绿

- [ ] **Step 8: 写执行器侧测试**

追加到 `backend/tests/test_ai_pending.py`：

```python
async def test_approve_add_lunar_date_creates_it(db_session, make_user):
    """确认加农历生日：落库后能经 get_contact 读回，农历字段正确。"""
    from app.modules.contacts import service as contacts_service

    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴")
    action = await pending_service.propose(
        db_session,
        demo,
        "add_important_date",
        {
            "contact_id": contact.id,
            "type": "birthday",
            "calendar": "lunar",
            "lunar_month": 9,
            "lunar_day": 24,
            "lunar_is_leap": False,
            "yearly": True,
            "reminder_lead_days": [7, 1],
        },
    )

    result = await pending_service.approve(db_session, demo, action.id)

    assert result.result["ok"] is True
    detail = await contacts_service.get_contact(db_session, demo, contact.id)
    assert [(d.lunar_month, d.lunar_day) for d in detail.dates] == [(9, 24)]


async def test_approve_delete_missing_date_records_failure(db_session, make_user):
    """提议引用的日期已被删：记 ok=False，不 500 卡在 pending。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴")
    action = await pending_service.propose(
        db_session,
        demo,
        "delete_important_date",
        {"contact_id": contact.id, "date_id": 999999},
    )

    result = await pending_service.approve(db_session, demo, action.id)

    assert result.status == "executed"
    assert result.result["ok"] is False
```

- [ ] **Step 9: 跑测试确认通过并全量回归**

```bash
cd backend && uv run pytest -q && uv run ruff check .
```

预期：全绿

- [ ] **Step 10: 提交**

```bash
git add backend/app/modules/ai/registry.py backend/app/modules/ai/executors backend/tests/test_ai_tools.py backend/tests/test_ai_pending.py
git commit -m "feat(ai): 重要日期三件套（加/改/删），支持农历"
```

---

## Task 10: 寻址硬切成 id + 提示词的改/删纪律

**Files:**
- Modify: `backend/app/modules/ai/registry.py`（`CreateTaskArgs`、`CreateActivityArgs`、`ContactTimelineArgs` 三个 schema 与对应处理函数；删 `resolve_contact_name`）
- Modify: `backend/app/modules/ai/executors/tasks.py`、`activities.py`（改用 `contact_id`）
- Delete: `backend/app/modules/ai/executors/common.py`（`resolve_contact_id` 随之失去调用方）
- Modify: `backend/agent/runner.py`（`SYSTEM_PROMPT` 补改/删纪律与多命中确认）
- Test: `backend/tests/test_ai_tools.py`、`backend/tests/test_ai_registry.py`

**Interfaces:**
- Consumes: 无新依赖
- Produces: `CreateTaskArgs.contact_id: int | None`、
  `CreateActivityArgs.participant_ids: list[int]`、`ContactTimelineArgs.contact_id: int`；
  所有工具入参 schema 一律 `extra="forbid"`

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_ai_registry.py`：

```python
def test_every_args_schema_forbids_extra_fields():
    """所有入参 schema 必须 forbid extra。

    寻址从名字改成 id 后，旧字段名（contact_name）若被静默忽略，
    模型会得到"成功建了一条没关联联系人的待办"这种安静的错误数据。
    forbid 让它当场报错，模型能立刻改。
    """
    offenders = [
        tool.name
        for tool in registry.ALL_TOOLS
        if tool.args_schema.model_config.get("extra") != "forbid"
    ]
    assert offenders == [], f"以下工具的入参 schema 未 forbid extra：{offenders}"
```

追加到 `backend/tests/test_ai_tools.py`：

```python
async def test_create_task_links_contact_by_id(db_session, make_user):
    """建待办用 contact_id 关联：id 无歧义，同名联系人不会挂错。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴")

    await _run_tool(db_session, demo, "create_task", title="打电话", contact_id=contact.id)

    action = (await pending_service.list_pending(db_session, demo))[0]
    assert action.payload["contact_id"] == contact.id


async def test_create_task_rejects_old_contact_name_field(db_session, make_user):
    """旧字段 contact_name 必须以报错的方式暴露，不能静默建出一条没关联人的待办。"""
    demo, _ = await make_user(username="demo")

    with pytest.raises(ValidationError):
        await _run_tool(db_session, demo, "create_task", title="打电话", contact_name="唐琴")


async def test_contact_timeline_by_id(db_session, make_user):
    """时间线按 id 查：不再有"按名字取第一个"的静默歧义。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴")

    text = await _run_tool(db_session, demo, "get_contact_timeline", contact_id=contact.id)

    assert "唐琴" in text
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_ai_registry.py tests/test_ai_tools.py -q -k "forbid_extra or by_id or old_contact_name"
```

预期：三条失败（`contact_id` 未知字段被忽略 / `extra` 配置不是 `forbid`）

- [ ] **Step 3: 改三个 schema，全部 forbid extra**

```python
class CreateTaskArgs(BaseModel):
    """建待办入参（写入确认队列）。"""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    contact_id: int | None = Field(default=None, description="关联联系人 id（先用 list_contacts 拿）")
    due_date: str | None = Field(default=None, description="截止日 YYYY-MM-DD（可选）")


class CreateActivityArgs(BaseModel):
    """记活动入参（写入确认队列）。"""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    occurred_date: str = Field(description="活动日期 YYYY-MM-DD")
    participant_ids: list[int] = Field(
        default_factory=list, description="参与者联系人 id（先用 list_contacts 拿）"
    )
    location: str | None = Field(default=None, max_length=200)


class ContactTimelineArgs(BaseModel):
    """联系人时间线入参。"""

    model_config = ConfigDict(extra="forbid")

    contact_id: int


```

`SearchContactsArgs` 已在 Task 7 删除，此处不再出现。

然后给**其余尚未 forbid 的 schema** 逐个补 `model_config = ConfigDict(extra="forbid")`，逐个列清以免漏掉：

| schema | 出处 |
|---|---|
| `CreateContactArgs` | 既有 |
| `KinshipArgs` | 既有 |
| `SemanticSearchArgs` | 既有 |
| `EmptyArgs` | 既有，被 `get_upcoming_todos` 与 `get_stats` 两个无参工具共用 |
| `ListContactsArgs` | Task 7 |
| `GetContactArgs` | Task 7 |
| `ContactIdArgs` | Task 8 |
| `UpdateContactArgs` / `AddImportantDateArgs` / `UpdateImportantDateArgs` / `DateIdArgs` | 已在各自任务里带上 |

改完必须跑 `tests/test_ai_registry.py::test_every_args_schema_forbids_extra_fields`——它就是这个清单的机器版本，漏掉任何一个都会红。

- [ ] **Step 4: 改处理函数与执行器**

`_run_queue_create_task` 里把 `contact_name` 换成 `contact_id`：

```python
    payload: dict[str, Any] = {"title": args.title}
    if args.contact_id is not None:
        payload["contact_id"] = args.contact_id
    if args.due_date:
        payload["due_at"] = args.due_date
```

`_run_queue_create_activity` 把 `participant_names` 换成 `participant_ids`（值直接进 payload）。

`_run_contact_timeline` 去掉名字解析，直接用 id：

```python
async def _run_contact_timeline(db: AsyncSession, user, args: ContactTimelineArgs) -> str:
    """按 id 查联系人的最近往来（时间线聚合前 10 条）。"""
    try:
        detail = await contacts_service.get_contact(db, user, args.contact_id)
    except NotFoundError:
        return f"没有找到 id={args.contact_id} 的联系人"
    timeline = await dashboard_service.build_contact_timeline(db, user, args.contact_id)
    if not timeline.items:
        return f"{detail.display_name} 暂无往来记录"
    lines = []
    for item in timeline.items[:10]:
        day = item.occurred_at.date().isoformat()
        amount = f"，{item.amount} 元" if item.amount else ""
        lines.append(f"- {day} [{item.source}] {item.title}{amount}")
    return f"{detail.display_name} 的最近往来：\n" + "\n".join(lines)
```

`executors/tasks.py::create_task` 把 `await resolve_contact_id(db, user, payload)` 换成直接读 `payload.get("contact_id")`；`executors/activities.py::create_activity` 把名字解析换成 `payload.get("participant_ids", [])`（`ActivityCreate.participant_contact_ids` 接收）。

- [ ] **Step 5: 删掉失去调用方的名字解析**

从 `registry.py` 删除 `_resolve_contact_by_name` 与 `resolve_contact_name`；删除 `executors/common.py` 整个文件（`resolve_contact_id` 已无调用方）。若 `executors/` 下还有别的共用助手则保留该文件，否则删。

改完跑 `uv run ruff check .`，它会报出所有残留的未使用 import 与悬空引用，逐个清掉。

- [ ] **Step 6: 改写提示词**

`backend/agent/runner.py` 的 `SYSTEM_PROMPT` 改为：

```python
SYSTEM_PROMPT = """你是「个人名册」家庭关系管理系统的助理，帮助家庭成员查看和维护人脉信息。

回答原则：
1. 一切涉及用户数据的问题（联系人、待办、往来、统计），必须先调用工具查询，禁止凭空编造或猜测。
2. 按问题选择合适的工具，能一步到位就不要多步：
   - 统计与名单类问题（"半年没联系的人""最近联系过谁"）→ get_stats（已含名单，一次即可）
   - 找某个人的信息 → list_contacts（拿到 id）→ get_contact（读完整资料）
   - 某人的交往记录 → get_contact_timeline
   - 临近的事 → get_upcoming_todos
3. **一切写入都按 id 寻址**：先用 list_contacts 拿 contact_id，再把 id 传给写工具；
   不要用姓名寻址，也不要把名字塞进 id 字段。
4. **改之前必须先读**：改联系人先 get_contact 回读现状，改日期先看 get_contact 返回的
   重要日期列表。看到现状才谈得上改，凭空改写会覆盖掉用户已有的信息。
5. **找不到既有记录时，报告并询问，不要改用新建绕过**：如果用户说要改某人，而 list_contacts
   找不到他，就如实说明并问用户是不是要新建——直接用 create 绕过会建出重复的人。
6. **读到多条候选时必须复述给用户确认**，列出每条的 id 与可区分字段（单位、记录人…），
   让用户指定改哪一个；禁止自己挑一条就动手。
7. 写入操作会先进入待确认队列，你需要告知用户"已生成提议，请在确认面板确认"；
   删除类操作要在回复里复述将被删除的对象。
8. 用简体中文回答，简洁口语化；数字与姓名必须来自工具结果，不得虚构。
9. 用户发来名片/聊天截图要求录入时：先用 list_contacts 查同名，再调
   create_contact 生成提议（需用户确认后生效）；图里没有的字段留空，禁止编造。"""
```

- [ ] **Step 7: 跑测试确认通过**

```bash
cd backend && uv run pytest -q && uv run ruff check .
```

预期：全绿

- [ ] **Step 8: 浏览器端到端核验**

```bash
./dev.sh
```

在 http://localhost:5180 助理页依次验证（这是本阶段的验收标准）：

1. 「唐琴的电话改成 13900000000」→ 助理先 `list_contacts`/`get_contact`，再生成**修改**提议，面板显示 `电话: 138… → 139…`（而不是"建联系人"）；
2. 「给唐琴加一条农历九月廿四的生日」→ 生成加重要日期提议，确认后详情页往来区上方出现该日期；
3. 「把唐琴升级为直接联系人」→ 生成升级提议；
4. 同一轮里产生多条提议时，勾选两条点「确认选中」，两条都执行且各自显示结果；
5. 故意说「改一下张三的资料」（名册里没有张三）→ 助理应**报告找不到并询问**，而不是直接建人。

- [ ] **Step 9: 更新接口地图**

`ARCHITECTURE.md` 第 4 节 `/mcp` 那一行改为：

```markdown
| /api/v1/ai、/mcp | ai | ✅ 52 工具（读直执行 / 写全进确认队列，D24）；`/mcp` Streamable HTTP（对外，JWT 或个人令牌门卫）… |
```

并把该行原有的工具举例改为指向 D24 与 spec，避免接口地图随工具增加而反复改。

- [ ] **Step 10: 提交**

```bash
git add backend/app/modules/ai backend/agent/runner.py backend/tests ARCHITECTURE.md
git commit -m "feat(ai): 寻址统一为 contact_id（硬切），提示词补改/删纪律与多命中确认"
```

---

## 本计划与 spec 的覆盖对照

| Spec 章节 | 落点 |
|---|---|
| §2.2 风险档位不变 | 全局约束；Task 3 的 `test_read_tools_have_no_executor` |
| §2.3 寻址硬切、不留兼容层 | Task 10 |
| §2.5 label 下移到 `AiTool` | Task 1、Task 2 |
| §2.6 `pending_actions.preview` | Task 4 |
| §3.2 读工具（本阶段 2 个） | Task 7 |
| §3.3 写工具（本阶段 8 个） | Task 8（3）、Task 9（3）、+ 既有 3 个的寻址改造（Task 10） |
| §3.4 多命中处置 | Task 7（返回格式带 id 与可区分字段）、Task 10（提示词第 6 条） |
| §3.5 删 `search_contacts` | Task 7 |
| §4.1 `AiTool` 扩展 | Task 1 |
| §4.2 执行器（含拆包） | Task 5 |
| §4.3 preview 快照 | Task 4、Task 8、Task 9 |
| §4.4 同名解析改为显式报错 | Task 10（该函数随 id 寻址整体删除，比保留更彻底） |
| §4.5 系统提示词增补 | Task 10 Step 6 |
| §5 前端：label 消费 + 差异渲染 | Task 2、Task 6 |
| §5.1 批量确认 | Task 6 |
| §6 测试（契约 + 行为） | Task 3（契约）、Task 7/8/9/10（行为） |
| §7 文档登记 | Task 0（TECH_DECISIONS D24 + ROADMAP）、Task 4 Step 3b（DATA_MODEL 的 preview 列）、Task 10 Step 9（ARCHITECTURE 接口地图） |
| §10 阶段 1–2 | 全部 10 个任务 |
| §10 阶段 3–5 | **不在本计划**，见开头「本计划只覆盖阶段 1–2」 |
