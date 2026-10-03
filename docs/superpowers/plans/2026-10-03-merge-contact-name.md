# 姓名模型合并为单字段（D23）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `contacts` 表的 `last_name` + `first_name` 合并为单列 `name`，并删除死字段 `display_name_override`，姓名模型收敛为 `name` + `nickname`。

**Architecture:** 一次迁移完成「加列 → 回填 → 删三列」，接口契约同步硬切（不留兼容层）。检索与同名检测随之简化：搜索由 4 个 `ilike` 降为 2 个；同名检测由「姓+名拼成全等」降为单列全等。

**Tech Stack:** FastAPI + SQLAlchemy 2.x（async）+ Alembic + PostgreSQL 16；Vue 3 + TypeScript + Element Plus + Vitest。

**Spec:** `docs/superpowers/specs/2026-10-03-merge-contact-name-design.md`

## Global Constraints

- **测试库独立**：`personal_crm_test`（宿主 5433），由 `tests/conftest.py:8` 的 `setdefault` 覆盖。测试建表走 `Base.metadata.create_all`（conftest.py:44），**不跑迁移**——迁移必须单独手工验证。
- **迁移放** `backend/alembic/versions/`（ruff 已排除该目录）；`down_revision = "b8e9d4f3a276"`。
- **`name` 列定义**：`VARCHAR(100) NOT NULL DEFAULT ''`，注释「姓名（中文姓名整体存储，D23）」。100 = 原 `50 + 50` 上界，不缩水。
- **展示名规则**（唯一实现点 `contacts.models.Contact.display_name`）：`nickname > name > "（未命名）"`。
- **回填 SQL（逐字）**：`UPDATE contacts SET name = trim(coalesce(last_name, '')) || trim(coalesce(first_name, ''))`
- **写入不做规范化**：`name` 原样入库（与旧行为一致，旧代码也不 strip 姓/名），首尾空白只在 `display_name` 读取时 strip。
- **不动**：`nickname` 列、`visibility`/`status`/`owner_user_id` 等混入字段、前端列表页姓名列（渲染 `row.display_name`）、`docs/superpowers/specs/2026-09-29-vision-import-design.md`（带日期历史文档，不改写）。
- **命令**：后端一律 `uv run ...`（依赖已装好）；前端 `npm run test` / `npm run build`。
- 环境纪律：开发环境已在跑（宿主 uvicorn 8100 + Vite 5180 + db 容器）。**不要** rebuild 镜像、不要动测试/生产环境。

## Review Focus

spec 是愿景文档，以下 5 类是它没说、但最可能咬到真实使用者的输入，按可能性排序。每行都指明了归属任务与处置方式：

1. **新建时 `name` 为空串（只填昵称的 edge 联系人）→ 同名检测必须跳过姓名条件**。若照抄旧代码把「空串」当有效值去比 `Contact.name == ""`，所有只填昵称的联系人会互相误拦，第二个 edge 联系人就建不出来。归属 Task 1，**有测试** `test_duplicate_check_skips_blank_name`。
2. **存量中 `display_name_override` 有值的行**，删列后展示名回退到 `nickname > name`，这些人的显示名会变。**接受此变化，无测试**——该字段前端从无填写入口（只可能被直接调 API 写脏），迁移文件内注释登记。
3. **回填保留姓/名的首尾空白**（用 `trim()` 消除）。**归属 Task 1 的迁移验证步骤**：`trim(coalesce(' 陈 ','')) || trim(coalesce('建国 ',''))` 必须得 `陈建国`，且 `alembic upgrade head` 后 dev 库既有种子行读出 `name = '陈建国'`。
4. **原 50+50 拼满 100 字符的存量行**必须完整装入 `name(100)`，不截断。归属 Task 1，**有测试** `test_name_length_boundary`（100 字过、101 字 422）。
5. **`name` 为纯空白（`"   "`）且无昵称** → 创建被拒 422，而不是存进去变成「（未命名）」。归属 Task 1，**有测试**（`test_display_name_rule` 的第三段）。

---

### Task 1: contacts 后端模块单字段化（模型 / 迁移 / 契约 / 检索）

**Files:**
- Modify: `backend/app/modules/contacts/models.py:41-52`（字段）、`backend/app/modules/contacts/models.py:98-104`（`display_name`）
- Modify: `backend/app/modules/contacts/schemas.py:28-34`（ContactBase）、`schemas.py:70-82`（ContactCreate 校验）、`schemas.py:84-100`（ContactUpdate）、`schemas.py:104-115`（ContactOut）
- Modify: `backend/app/modules/contacts/repository.py:36-64`（搜索）、`repository.py:173-206`（同名检测）
- Modify: `backend/app/modules/contacts/service.py:89-104`（check_duplicates / create_contact）
- Modify: `backend/app/modules/contacts/api.py:28-37`（duplicate-check）
- Create: `backend/alembic/versions/<rev>_merge_contact_name_d23.py`
- Test: `backend/tests/test_contacts.py`

**Interfaces:**
- Consumes: 无（本任务是链条起点）
- Produces（后续任务按此签名调用）：
  - `Contact.name: Mapped[str]` — VARCHAR(100) NOT NULL DEFAULT ''
  - `Contact.display_name -> str` — `nickname > name > "（未命名）"`
  - `ContactCreate`（含 `name: str = ""`、`nickname: str | None`、`confirm_duplicate: bool = False`）
  - `ContactUpdate`（含 `name: str | None`）
  - `ContactOut`（含 `name: str`、`nickname: str | None`、`display_name: str`）
  - `contact_repo.find_family_duplicates(db, user, *, name: str, nickname: str | None, exclude_contact_id: int | None = None) -> list[tuple[Contact, str]]`
  - `contact_service.check_duplicates(db, user, name: str, nickname: str | None) -> list[DuplicateWarning]`
  - `GET /api/v1/contacts/duplicate-check?name=&nickname=`

- [ ] **Step 1: 改写 test_contacts.py 到新契约（先红）**

逐处替换（保留其余断言不变）：

| 行 | 原文 | 改为 |
|---|---|---|
| 28 | `create_contact_for(owner, last_name="陈", first_name="建国", nickname="老爸")` | `create_contact_for(owner, name="陈建国", nickname="老爸")` |
| 60 | `json={"tier": "direct", "last_name": "陈", "first_name": "建国", "nickname": "老爸"}` | `json={"tier": "direct", "name": "陈建国", "nickname": "老爸"}` |
| 60 后新增断言 | — | `assert body["contact"]["name"] == "陈建国"` |
| 88 | `payload = {"last_name": "张", "first_name": "伟", "nickname": None}` | `payload = {"name": "张伟", "nickname": None}` |
| 109 | `owner, last_name="张", first_name="伟", visibility="family"` | `owner, name="张伟", visibility="family"` |
| 133 | `owner, last_name="周", first_name="明", visibility="private"` | `owner, name="周明", visibility="private"` |
| 148 | `owner, tier="edge", nickname="张小宝", first_name="小宝"` | `owner, tier="edge", nickname="张小宝", name="小宝"` |
| 161 | `owner, last_name="王", first_name="芳", tier="edge"` | `owner, name="王芳", tier="edge"` |
| 178 | `create_contact_for(owner, last_name="陈", first_name="建国", nickname="老爸")` | `create_contact_for(owner, name="陈建国", nickname="老爸")` |

`test_search_matches_nickname` 与 `test_create_edge_contact_minimal_fields` 只改上面表里的构造调用，断言不动（后者本就只有 `nickname`）。

然后在文件末尾追加 5 个新用例：

```python
async def test_search_matches_name(client, family_users):
    """搜索命中姓名（单字段模糊匹配，不再拆姓/名两个条件）。"""
    owner, _ = family_users
    await create_contact_for(owner, name="陈建国", nickname="老爸")
    headers = await login_as(client, "demo", "demo12345")
    response = await client.get("/api/v1/contacts", params={"search": "建国"}, headers=headers)
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["name"] == "陈建国"


async def test_duplicate_check_skips_blank_name(client, family_users):
    """姓名留空（只填昵称的 edge 联系人）时同名检测必须跳过姓名条件。

    否则 Contact.name == "" 会命中所有同样留空的 edge 联系人，第二个就建不出来。
    """
    owner, _ = family_users
    await create_contact_for(owner, tier="edge", nickname="张小宝")
    headers = await login_as(client, "demo", "demo12345")

    created = await client.post(
        "/api/v1/contacts", json={"tier": "edge", "nickname": "李二"}, headers=headers
    )
    assert created.json()["created"] is True
    assert created.json()["duplicate_warnings"] == []

    probed = await client.get(
        "/api/v1/contacts/duplicate-check",
        params={"name": "", "nickname": "李二"},
        headers=headers,
    )
    assert probed.status_code == 200
    assert probed.json() == []


async def test_display_name_rule(client, family_users):
    """展示名规则：昵称 > 姓名；姓名与昵称都空（含纯空白）则创建被拒 422。"""
    owner, _ = family_users
    headers = await login_as(client, "demo", "demo12345")

    with_nickname = await client.post(
        "/api/v1/contacts", json={"name": "陈建国", "nickname": "老爸"}, headers=headers
    )
    assert with_nickname.json()["contact"]["display_name"] == "老爸"

    name_only = await client.post(
        "/api/v1/contacts", json={"name": "陈秀兰"}, headers=headers
    )
    assert name_only.json()["contact"]["display_name"] == "陈秀兰"

    blank = await client.post("/api/v1/contacts", json={"name": "   "}, headers=headers)
    assert blank.status_code == 422


async def test_name_length_boundary(client, family_users):
    """姓名列上限 100（原 姓50+名50 的上界不缩水）：满 100 可存，101 被拒。"""
    owner, _ = family_users
    headers = await login_as(client, "demo", "demo12345")

    full = "欧" * 100
    ok = await client.post("/api/v1/contacts", json={"name": full}, headers=headers)
    assert ok.status_code == 200
    assert ok.json()["contact"]["name"] == full

    too_long = await client.post("/api/v1/contacts", json={"name": "欧" * 101}, headers=headers)
    assert too_long.status_code == 422


async def test_update_name(client, family_users):
    """改名走 PATCH：单字段更新后展示名与搜索结果同步。"""
    owner, _ = family_users
    contact = await create_contact_for(owner, name="陈建国")
    headers = await login_as(client, "demo", "demo12345")

    updated = await client.patch(
        f"/api/v1/contacts/{contact.id}", json={"name": "陈建军"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "陈建军"
    assert updated.json()["display_name"] == "陈建军"

    found = await client.get("/api/v1/contacts", params={"search": "建军"}, headers=headers)
    assert [r["id"] for r in found.json()] == [contact.id]
```

- [ ] **Step 2: 跑测试确认红**

Run: `cd backend && uv run pytest tests/test_contacts.py -q`
Expected: FAIL — `TypeError: 'name' is an invalid keyword argument for Contact()`（模型还没有 `name` 列），`test_search_matches_nickname` 等旧断言也一并失败。

- [ ] **Step 3: 改模型（models.py）**

字段区：删掉 `last_name`、`first_name`、`display_name_override` 三列的 `mapped_column`，换成一列；`nickname` 的注释补上语义：

```python
    name: Mapped[str] = mapped_column(
        String(100),
        default="",
        server_default="",
        comment="姓名（中文姓名整体存储，D23）",
    )
    nickname: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="昵称/称呼（外号、亲近称呼）"
    )
```

`display_name` property 全文替换：

```python
    @property
    def display_name(self) -> str:
        """展示名规则（唯一实现点，DATA_MODEL.md 第 2 节）：昵称 > 姓名 > 「（未命名）」。"""
        if self.nickname and self.nickname.strip():
            return self.nickname.strip()
        return self.name.strip() or "（未命名）"
```

- [ ] **Step 4: 改契约（schemas.py）**

`ContactBase`：三行换一行

```python
    name: str = Field(default="", max_length=100)
    nickname: str | None = Field(default=None, max_length=100)
```

`ContactCreate.validate_name_presence`：

```python
    @model_validator(mode="after")
    def validate_name_presence(self) -> "ContactCreate":
        """至少能定位到一个人：姓名、昵称必有其一。"""
        if not any([self.name.strip(), (self.nickname or "").strip()]):
            raise ValueError("姓名、昵称至少填写一项")
        return self
```

`ContactUpdate`：三行换一行

```python
    name: str | None = Field(default=None, max_length=100)
```

`ContactOut`：三行换一行

```python
    name: str
```

- [ ] **Step 5: 写迁移**

Run: `cd backend && uv run alembic revision -m "merge contact name fields d23"` 生成骨架，然后把内容整体替换为（`<rev>` 用生成的文件名里的 hash）：

```python
"""merge contact name fields d23

Revision ID: <rev>
Revises: b8e9d4f3a276
Create Date: 2026-10-03

D23：姓名单字段化。last_name + first_name → name，并删除死字段 display_name_override。
"""

import sqlalchemy as sa
from alembic import op

revision = "<rev>"
down_revision = "b8e9d4f3a276"
branch_labels = None
depends_on = None

# 先 trim 再拼：旧数据里姓/名任一首尾带空格时，直接拼接会得到「陈 建国」这种
# 内部带空格的姓名，展示与搜索都会失配。
_BACKFILL = (
    "UPDATE contacts SET name = "
    "trim(coalesce(last_name, '')) || trim(coalesce(first_name, ''))"
)


def upgrade() -> None:
    """加 name → 回填 → 删三列。顺序不可换，换了两列数据就没了。"""
    op.add_column(
        "contacts",
        sa.Column(
            "name",
            sa.String(length=100),
            nullable=False,
            server_default="",
            comment="姓名（中文姓名整体存储，D23）",
        ),
    )
    op.execute(_BACKFILL)
    # display_name_override 的用户数据在此丢弃：该字段前端从无填写入口，
    # 存量若有值（只可能来自直接调 API），这些联系人删列后展示名回退到 nickname > name。
    op.drop_column("contacts", "display_name_override")
    op.drop_column("contacts", "first_name")
    op.drop_column("contacts", "last_name")


def downgrade() -> None:
    """不可逆：整名无法可靠拆回姓/名（「陈建国」该拆成 陈+建国 还是 陈建+国？）。

    只还原列结构：整名整体存入 last_name（超 50 字符按 left(50) 截断，否则列宽不足报错），
    first_name 置空，display_name_override 保持 NULL。
    """
    op.add_column(
        "contacts",
        sa.Column(
            "last_name", sa.String(length=50), nullable=False, server_default="", comment="姓"
        ),
    )
    op.add_column(
        "contacts",
        sa.Column(
            "first_name", sa.String(length=50), nullable=False, server_default="", comment="名"
        ),
    )
    op.add_column(
        "contacts",
        sa.Column(
            "display_name_override",
            sa.String(length=100),
            nullable=True,
            comment="手动指定展示名，优先级最高",
        ),
    )
    op.execute("UPDATE contacts SET last_name = left(name, 50)")
    op.drop_column("contacts", "name")
```

- [ ] **Step 6: 改检索与同名检测（repository.py）**

搜索条件（`find_readable_contacts` 内）：四条件降两条件，并把函数 docstring 第 3 行的说明改为「search 同时模糊匹配 姓名/昵称」：

```python
        stmt = stmt.where(
            Contact.name.ilike(pattern) | Contact.nickname.ilike(pattern)
        )
```

`find_family_duplicates` 整体替换（注意 `cleaned_name` 的空值守卫是 Review Focus 第 1 条，**不能省**）：

```python
async def find_family_duplicates(
    db: AsyncSession,
    user,
    *,
    name: str,
    nickname: str | None,
    exclude_contact_id: int | None = None,
) -> list[tuple[Contact, str]]:
    """家庭范围内同名检测（D7 细化）：命中"姓名"全等或昵称全等的在册联系人。

    返回 (联系人, 所有者展示名) 行，供 service 直接组装提醒。
    姓名为空时跳过姓名条件——否则会命中所有姓名同样为空的 edge 联系人（只填了昵称的那些）。
    """
    cleaned_name = name.strip()
    cleaned_nickname = (nickname or "").strip()

    match_conditions = []
    if cleaned_name:
        match_conditions.append(Contact.name == cleaned_name)
    if cleaned_nickname:
        match_conditions.append(Contact.nickname == cleaned_nickname)
    if not match_conditions:
        return []

    stmt = (
        select(Contact, User.display_name.label("owner_display_name"))
        .join(User, User.id == Contact.owner_user_id)
        .where(
            readable_condition(Contact, user),
            Contact.status == "active",
            *match_conditions,
        )
        .limit(5)
    )
    if exclude_contact_id is not None:
        stmt = stmt.where(Contact.id != exclude_contact_id)
    return [(row[0], row[1]) for row in (await db.execute(stmt)).all()]
```

- [ ] **Step 7: 改服务层与路由（service.py / api.py）**

`service.check_duplicates` 与 `create_contact` 的调用：

```python
async def check_duplicates(
    db: AsyncSession, user: User, name: str, nickname: str | None
) -> list[DuplicateWarning]:
    """同名检测（D7 细化）：家庭范围内命中即返回提醒列表。"""
    hits = await contact_repo.find_family_duplicates(db, user, name=name, nickname=nickname)
    return [_build_warning(contact, owner_name) for contact, owner_name in hits]
```

```python
    warnings = await check_duplicates(db, user, data.name, data.nickname)
```

`api.py` 的 duplicate-check：

```python
@router.get("/duplicate-check", response_model=list[DuplicateWarning])
async def check_duplicate(
    name: str = "",
    nickname: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DuplicateWarning]:
    """输入过程中的实时同名提示（表单失焦时调用）。"""
    return await contact_service.check_duplicates(db, current_user, name, nickname)
```

- [ ] **Step 8: 跑测试确认绿**

Run: `cd backend && uv run pytest tests/test_contacts.py -q`
Expected: PASS（全部用例）
再跑：`uv run ruff check app/modules/contacts/`
Expected: 无输出

- [ ] **Step 9: 手工验证迁移（pytest 不跑迁移，必须单独验）**

```bash
cd backend
# 1) 回填表达式本身（钉住 trim 行为）
docker compose -f ../docker-compose.yml exec -T db \
  psql -U crm -d personal_crm \
  -c "SELECT trim(coalesce(' 陈 ','')) || trim(coalesce('建国 ','')) AS backfilled;"
# Expected: backfilled = 陈建国

# 2) 迁移上下都能跑
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head

# 3) 存量种子数据的回填结果（dev 库已有 seed 数据）
uv run python -c "
import asyncio
from sqlalchemy import text
from app.core.db import get_session_factory
async def main():
    async with get_session_factory()() as s:
        rows = (await s.execute(text('select name, nickname from contacts order by id limit 3'))).all()
        print(rows)
asyncio.run(main())
"
# Expected: 第一条为 ('陈建国', '老爸') 之类——姓与名已拼成整名，昵称列不受影响
# 若 dev 库 contacts 为空，本步改为下一任务跑完 seed 后复核
```

- [ ] **Step 10: 提交**

```bash
git add backend/app/modules/contacts backend/alembic/versions backend/tests/test_contacts.py
git commit -m "feat(contacts): 姓名合并为单字段 name（D23）

last_name + first_name → name(VARCHAR 100)，删除死字段 display_name_override。
展示名规则简化为 nickname > name > 「（未命名）」；
搜索四条件降两条件；同名检测由拼接全等降为单列全等，
并保留空名守卫，避免只填昵称的 edge 联系人互相误拦。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: AI / MCP 工具契约与对话测试

**Files:**
- Modify: `backend/app/modules/ai/registry.py:70-95`（CreateContactArgs）、`registry.py:189-213`（`_run_queue_create_contact`）
- Test: `backend/tests/test_ai_pending.py:19,100,121,125`、`backend/tests/test_ai_tools.py`（10 处）、`backend/tests/test_ai_chat.py:107`

**Interfaces:**
- Consumes: Task 1 的 `ContactCreate`（`name` + `nickname`）；`contacts_service.create_contact`（`EXECUTORS` 里的既有调用，签名不变）
- Produces: `CreateContactArgs.name: str = ""`；MCP `create_contact` 工具入参 `name`（原 `last_name`/`first_name` 消失）

- [ ] **Step 1: 改测试到新契约（先红）**

`test_ai_pending.py`：

| 行 | 原文 | 改为 |
|---|---|---|
| 19 | `create_contact_for(demo, last_name="陈", first_name="建国", nickname="老爸")` | `create_contact_for(demo, name="陈建国", nickname="老爸")` |
| 100 | `{"tier": "direct", "last_name": "王", "nickname": "王姨", "phone": "13800000000"}` | `{"tier": "direct", "name": "王", "nickname": "王姨", "phone": "13800000000"}` |
| 121 | `create_contact_for(demo, last_name="王", first_name="", nickname="王姨")` | `create_contact_for(demo, name="王", nickname="王姨")` |
| 125 | `{"tier": "direct", "last_name": "王", "nickname": "王姨"}` | `{"tier": "direct", "name": "王", "nickname": "王姨"}` |

`test_ai_chat.py:107`：`create_contact_for(demo, last_name="陈", first_name="建国", nickname="老爸")` → `create_contact_for(demo, name="陈建国", nickname="老爸")`

`test_ai_tools.py` 共 10 处，逐行替换（其余参数原样保留；前 8 处是 ORM 工厂调用，后 2 处是 `_run_tool` 的工具入参，都在本任务范围内）：

| 行 | 原姓名参数 | 替换为 |
|---|---|---|
| 47 | `last_name="陈", first_name="建国"` | `name="陈建国"` |
| 57 | `last_name="周", first_name="明"` | `name="周明"` |
| 77 | `last_name="陈", first_name="建国"` | `name="陈建国"` |
| 92 | `last_name="陈", first_name="建国"` | `name="陈建国"` |
| 125 | `last_name="陈", first_name="建国"` | `name="陈建国"` |
| 142 | `last_name="李", first_name="秀"` | `name="李秀"` |
| 143 | `last_name="李", first_name="大勇"` | `name="李大勇"` |
| 144 | `last_name="陈", first_name="小澄"` | `name="陈小澄"` |
| 187 | `last_name="王"`（`_run_tool` 入参，跨行缩进） | `name="王"` |
| 215 | `last_name="王"`（`_run_tool` 入参） | `name="王"` |

改完必须自检：

```bash
grep -rn --include="*.py" "last_name\|first_name" backend/tests/test_ai_*.py
```
Expected: 无输出

- [ ] **Step 2: 跑测试确认红**

Run: `cd backend && uv run pytest tests/test_ai_pending.py tests/test_ai_tools.py tests/test_ai_chat.py -q`
Expected: FAIL — `TypeError: 'name' is an invalid keyword argument for Contact()`（模型已改但 registry 的 payload 还在传 `last_name`/`first_name`；factories 改用 `name` 已能入库，所以失败点集中在工具契约用例）。

- [ ] **Step 3: 改工具入参（registry.py）**

`CreateContactArgs` 的姓名两行换一行，validator 同步：

```python
    name: str = Field(default="", max_length=100)
    nickname: str | None = Field(default=None, max_length=100)
```

```python
    @model_validator(mode="after")
    def validate_name_presence(self) -> "CreateContactArgs":
        """与 ContactCreate 同一最小信息集：姓名、昵称至少一项，否则没法定位到人。"""
        if not any([self.name.strip(), (self.nickname or "").strip()]):
            raise ValueError("姓名、昵称至少填写一项")
        return self
```

`_run_queue_create_contact` 的 payload 与回执文案：

```python
async def _run_queue_create_contact(db: AsyncSession, user, args: CreateContactArgs) -> str:
    """建联系人提议入队：payload 即联系人字段，同名拦截延后到确认执行时。"""
    from app.modules.ai import pending as pending_service

    payload: dict[str, Any] = {
        "tier": args.tier,
        "name": args.name,
    }
    for key in (
        "nickname", "organization", "phone", "qq",
        "wechat", "email", "school_name", "bio", "location",
    ):
        value = getattr(args, key)
        if value:
            payload[key] = value
    action = await pending_service.propose(db, user, "create_contact", payload)
    suffix = f"（{args.nickname}）" if args.nickname else ""
    return (
        f"已生成联系人提议（编号 {action.id}，待确认）：{args.name}{suffix}。"
        f"需要用户在界面确认后才会真正创建。"
    )
```

- [ ] **Step 4: 跑测试确认绿**

Run: `cd backend && uv run pytest tests/test_ai_pending.py tests/test_ai_tools.py tests/test_ai_chat.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/modules/ai/registry.py backend/tests/test_ai_pending.py backend/tests/test_ai_tools.py backend/tests/test_ai_chat.py
git commit -m "feat(ai): create_contact 工具入参改用 name（D23）

MCP 工具 schema 同步姓名单字段化，最小信息集与 ContactCreate 保持一致。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 其余测试机械替换 + 种子数据（全量后端绿）

**Files:**
- Modify: `backend/tests/test_contact_location.py`、`test_dashboard.py`、`test_dates.py`、`test_funds.py`、`test_gifts.py`、`test_graph.py`、`test_kinship_api.py`、`test_notes.py`、`test_records.py`、`test_semantic.py`、`test_stats.py`、`test_timeline.py`
- Modify: `backend/scripts/seed.py:112-146`

**Interfaces:**
- Consumes: Task 1 的 `Contact.name`
- Produces: 无（本任务是收敛任务，产出全绿的后端测试与一致的 demo 数据）

- [ ] **Step 1: 跑全量，记录红**

Run: `cd backend && uv run pytest -q`
Expected: FAIL — 上面 12 个文件里所有 `last_name=` / `first_name=` 调用报 `TypeError: 'name' is an invalid keyword argument`

- [ ] **Step 2: 批量替换（12 个文件）**

`tests/factories.py` 的 `create_contact_for(user, **fields)` 直接透传 ORM，姓名参数是在**每个调用点**写的，所以必须逐点替换。用脚本做（规则：`name` = 原 `last_name` + 原 `first_name`，保持原顺序；只有一个时取该值）：

```bash
cd backend && python3 - <<'PY'
import pathlib, re

FILES = [
    "tests/test_contact_location.py", "tests/test_dashboard.py", "tests/test_dates.py",
    "tests/test_funds.py", "tests/test_gifts.py", "tests/test_graph.py",
    "tests/test_kinship_api.py", "tests/test_notes.py", "tests/test_records.py",
    "tests/test_semantic.py", "tests/test_stats.py", "tests/test_timeline.py",
]

# 成对（允许姓名两参顺序颠倒，非贪婪且只跨空白，避免误吃跨调用的两处）
PAIR = re.compile(r'last_name=("([^"]*)"),\s*first_name=("([^"]*)")')
PAIR_REV = re.compile(r'first_name=("([^"]*)"),\s*last_name=("([^"]*)")')
LONE_LAST = re.compile(r'last_name=("([^"]*)")')
LONE_FIRST = re.compile(r'first_name=("([^"]*)")')

for name in FILES:
    path = pathlib.Path(name)
    text = path.read_text()
    before = text
    text = PAIR.sub(lambda m: f'name="{m.group(2)}{m.group(4)}"', text)
    text = PAIR_REV.sub(lambda m: f'name="{m.group(4)}{m.group(2)}"', text)
    text = LONE_LAST.sub(lambda m: f'name="{m.group(2)}"', text)
    text = LONE_FIRST.sub(lambda m: f'name="{m.group(2)}"', text)
    if text != before:
        path.write_text(text)
        print(f"改写 {name}")
PY
grep -rn --include="*.py" "last_name\|first_name" tests/ ; echo "退出码 $? （1 = 已无残留，符合预期）"
```

- [ ] **Step 3: 逐点复核拼接结果（脚本不做语义判断，必须人眼过）**

Run: `git diff backend/tests/ | grep "^+" | grep "name="`
逐条确认 `name` 的两个字符合并顺序与原 `last_name + first_name` 一致——尤其这几处已知的「非自然」姓名，是替换正确性的探针：

| 文件:行 | 替换前 | 替换后必须是 |
|---|---|---|
| `test_contact_location.py:49` | `first_name="阿", last_name="芳"` | `name="芳阿"`（顺序颠倒的调用点） |
| `test_kinship_api.py:92` | `last_name="王", first_name="同事"` | `name="王同事"` |
| `test_kinship_api.py:140` | `last_name="某", first_name="人"` | `name="某人"` |
| `test_graph.py:51` | `last_name="私", first_name="人"` | `name="私人"` |

任何断言的期望值若依赖旧展示名（如 `assert ... == "陈建国"`），保持字面量不变即可——拼接后仍是同一串。

- [ ] **Step 4: 跑全量确认绿**

Run: `cd backend && uv run pytest -q`
Expected: PASS（0 failed）
若仍有失败，逐条看是不是某个用例断言的是 `display_name` 而该联系人只有 `first_name`（旧规则会回退到「名」，新规则只有 `name`），按新契约修正断言。

- [ ] **Step 5: 改种子数据（seed.py）**

7 处联系人构造的姓名两参换一个（昵称/层级/可见性/简介等原样保留）：

```python
    father = Contact(
        owner_user_id=demo.id, family_id=family.id, name="陈建国",
        nickname="老爸", gender="male", visibility="family",
    )
    mother = Contact(
        owner_user_id=demo.id, family_id=family.id, name="陈秀兰",
        nickname="老妈", gender="female", visibility="family",
    )
    colleague = Contact(
        owner_user_id=demo.id, family_id=family.id, name="张伟",
        gender="male", organization="极星科技", visibility="family", bio="产品部同事，球友",
    )
    classmate = Contact(
        owner_user_id=wife.id, family_id=family.id, name="李娜",
        gender="female", visibility="family", bio="大学室友",
    )
    private_friend = Contact(
        owner_user_id=demo.id, family_id=family.id, name="周明",
        gender="male", visibility="private", bio="仅自己可见的示例",
    )
    # 边缘联系人（叶子）：张伟的妻子与儿子
    colleague_wife = Contact(
        owner_user_id=demo.id, family_id=family.id, tier="edge", name="王芳",
        gender="female", visibility="family",
    )
    colleague_son = Contact(
        owner_user_id=demo.id, family_id=family.id, tier="edge", nickname="张小宝",
        gender="male", visibility="family",
    )
    # "我"：demo 账号绑定的联系人节点（D15 视角推导起点）
    me = Contact(
        owner_user_id=demo.id, family_id=family.id, name="陈澄",
        nickname="阿澄", gender="male", visibility="family",
    )
```

Run: `cd backend && uv run python scripts/seed.py`
Expected: 无异常（dev 库已有数据，重复种子按脚本既有语义处理）

- [ ] **Step 6: 提交**

```bash
git add backend/tests backend/scripts/seed.py
git commit -m "test/seed: 测试与种子数据适配姓名单字段（D23）

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: 前端契约与页面

**Files:**
- Modify: `frontend/src/api/types.ts:44-99`（ContactOut / ContactCreate / ContactUpdate）
- Modify: `frontend/src/api/contacts.ts:33-40`（duplicateCheck 参数）
- Modify: `frontend/src/pages/ContactsPage.vue:33-36, 81-82, 97, 117-118, 283-287`
- Modify: `frontend/src/pages/ContactDetailPage.vue:60-63, 77-79, 100-101, 126-127, 608, 784-789`
- Modify: `frontend/src/components/AgentChat.vue:186-190`
- Test: `frontend/tests/agentChat.spec.ts:123`

**Interfaces:**
- Consumes: Task 1 的 `ContactOut.name`、`ContactCreate.name`、`ContactUpdate.name`、`GET /contacts/duplicate-check?name=`
- Produces: 前端全部页面消费 `contact.name`；`AgentChat` 确认面板把 `name` 渲染为「姓名」

- [ ] **Step 1: 改契约类型（types.ts）**

`ContactOut` 里三行换一行（顺序按现有字段位置）：

```ts
  name: string
```
（删 `last_name: string`、`first_name: string`、`display_name_override: string | null`；`nickname` / `display_name` 保留不动）

`ContactCreate` 里三行换一行：

```ts
  name?: string
```
（删 `last_name?: string`、`first_name?: string`、`display_name_override?: string | null`）

`ContactUpdate` 里两行换一行：

```ts
  name?: string
```
（删 `last_name?: string`、`first_name?: string`）

- [ ] **Step 2: 改接口封装（contacts.ts）**

```ts
  duplicateCheck: (params: { name?: string; nickname?: string | null }) => {
    const query = new URLSearchParams()
    if (params.name) query.set('name', params.name)
    if (params.nickname) query.set('nickname', params.nickname)
    const qs = query.toString()
    return api.get<DuplicateWarning[]>(`/contacts/duplicate-check${qs ? `?${qs}` : ''}`)
  },
```

（注：该函数目前全仓无调用点，改它是为了契约一致——新建流程走的是创建响应里的 `duplicate_warnings`。）

- [ ] **Step 3: 改名册页（ContactsPage.vue）**

`CreateForm` 接口：`last_name: string` / `first_name: string` 两行换 `name: string`
`form` 初值与 `resetForm()`：两行 `last_name: '', first_name: ''` 换 `name: ''`
`isSubmittable`：

```ts
const { capture, canSubmit } = useFormDirty(form, {
  isSubmittable: (draft) => draft.name.trim().length > 0,
})
```

模板里两个 `el-form-item` 合一：

```vue
        <el-form-item label="姓名">
          <el-input v-model="form.name" placeholder="如：陈建国" />
        </el-form-item>
```

（`submitCreate` 用 `...form.value` 展开，`name` 自动进 payload，无需改动。）

- [ ] **Step 4: 改详情页（ContactDetailPage.vue）**

`EditDraft` 接口与 `editDraft` 初值：`last_name`/`first_name` 两处换 `name`：
`openEdit()` 的 `last_name: c.last_name, first_name: c.first_name,` → `name: c.name,`
`submitEdit()` 的 `last_name: editDraft.value.last_name, first_name: editDraft.value.first_name,` → `name: editDraft.value.name,`
基本信息展示行：

```vue
            <el-descriptions-item label="姓名">{{ contact.name || '—' }}</el-descriptions-item>
```

编辑弹窗里 `.form-two-col` 包着「姓」「名」两个 `el-form-item`，改为 `.form-two-col` 外的一个：

```vue
          <el-form-item label="姓名">
            <el-input v-model="editDraft.name" placeholder="姓名" />
          </el-form-item>
```

- [ ] **Step 5: 改确认面板标签（AgentChat.vue）**

```ts
const CONTACT_FIELD_LABELS: Record<string, string> = {
  tier: '层级', name: '姓名', nickname: '昵称',
  organization: '单位', phone: '电话', qq: 'QQ', wechat: '微信',
  email: '邮箱', school_name: '院校', location: '所在地', bio: '备注',
}
```

- [ ] **Step 6: 改前端测试并跑**

`agentChat.spec.ts:123` 的 payload 改为 `{ tier: 'direct', name: '王', nickname: '王姨', phone: '13800000000' }`，并在该用例的断言里补一条钉住新标签：

```ts
    expect(text).toContain('姓名: 王')
```

Run: `cd frontend && npm run test`
Expected: PASS

- [ ] **Step 7: 类型检查与构建**

Run: `cd frontend && npm run build`
Expected: `vue-tsc -b` 无类型错误、`vite build` 产出 `dist/`。若报 `Property 'last_name' does not exist`，说明有页面漏改，按报错位置补 `name`。

- [ ] **Step 8: 手工核验（dev 环境已在跑）**

浏览器打开 http://localhost:5180 ，用 demo / demo12345 登录：
1. 名册页「记下一个人」→ 只有一个「姓名」输入框；填「陈建国」+ 昵称「老爸」能创建，列表显示「老爸」
2. 搜索框输入「建国」能搜到该联系人
3. 详情页「编辑资料」只有一个姓名框；改成「陈建军」保存后，详情与列表展示同步
4. 再建一个同名「陈建军」→ 出现同名提醒

- [ ] **Step 9: 提交**

```bash
git add frontend/src frontend/tests/agentChat.spec.ts
git commit -m "feat(frontend): 姓名单字段化，建人/编辑表单合一框（D23）

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: 事实源文档同步与 D23 登记

**Files:**
- Modify: `TECH_DECISIONS.md`（末尾追加 D23）
- Modify: `DATA_MODEL.md:56-59`（字段表）、`DATA_MODEL.md:80`（索引说明）、`DATA_MODEL.md:82`（展示名规则）
- Modify: `PROJECT_BACKGROUND.md:95`（R1 姓名需求）
- Modify: `ROADMAP.md:40`（联系人条目）

**Interfaces:**
- Consumes: Task 1–4 已落地的实现（文档描述必须与代码一致）
- Produces: 无代码影响

- [ ] **Step 1: 登记 D23（TECH_DECISIONS.md）**

在文件末尾追加（格式照 D22）：

```markdown
## D23 姓名模型合并为单字段（name）✅（2026-10-03）

- **背景**：`contacts` 原为 `last_name` + `first_name` 双列（PROJECT_BACKGROUND R1「姓、名分离存储」）。用户决策：中文姓名本就是一个整体，拆分只带来录入时的边界猜测（视觉导入、对话建人尤其明显），合并后存储与检索都更简单。
- **决策**：
  1. **单字段存储**：两列合并为 `name VARCHAR(100)`（原 50+50 上界不缩水）；不再拆分，**放弃姓氏排序与按姓生成称呼**——当前代码无任何一处单独使用「姓」（`graph/kinship.py` 的称谓走角色路径），故当下零功能损失。
  2. **一并删除 `display_name_override`**：前端从无填写入口的死字段，且与 `nickname` 职责重叠。姓名模型收敛为 `name` + `nickname`（外号/亲近称呼）。
  3. **展示名规则**：`nickname > name > 「（未命名）」`；实现点不变，仍是 `contacts.models.Contact.display_name`。
  4. **硬切不留兼容层**：单仓自托管、前端是唯一消费者；`/mcp` 的 `create_contact` 工具入参同步改为 `name`（工具 schema 由 `tools/list` 动态下发，无缓存问题）。
- **迁移**：加 `name` → 回填 `trim(coalesce(last_name,'')) || trim(coalesce(first_name,''))` → 删三列。**降级不可逆**（整名无法可靠拆回姓/名），降级只还原列结构、整名存入 `last_name`（超 50 字符截断）。
- **影响**：`ContactBase`/`Create`/`Update`/`Out` 三字段改 `name`；`GET /contacts/duplicate-check` 查询参数改 `name`；名册搜索由 4 条件降为 2；同名检测由「姓+名拼接全等」降为单列全等（顺带修掉「陈」+「建国」与「陈建」+「国」互相误判的老问题）。
```

- [ ] **Step 2: 改数据模型文档（DATA_MODEL.md）**

字段表两行换一行（第 56–57 行）：

```
| name | VARCHAR(100) NOT NULL DEFAULT '' | 姓名（中文姓名整体存储，D23；不再拆分姓/名） |
```

删除第 59 行的 `display_name_override` 行；`nickname` 行说明改为「昵称/称呼（外号、亲近称呼）」。

第 80 行索引说明改为：

```
索引：`(family_id, status)`、`(owner_user_id)`；同名检测按姓名全等查询，当前数据量走上述索引即可，不单建。`search_text` 生成列 + pg_trgm GIN 曾列入 Level 1 计划但从未实现（名册搜索走 `name`/`nickname` 的 ILIKE），需要全文检索时再补。
```

第 82 行展示名规则改为：

```
**展示名规则**（model property 唯一实现，禁在前端重复实现）：`nickname > name > 「（未命名）」`。
```

- [ ] **Step 3: 改需求基线（PROJECT_BACKGROUND.md:95）**

```
- **姓名**：中文姓名"姓+名"结构，需要原生建模。**（2026-10-03 修订，见 TECH_DECISIONS D23）**：姓名整体单字段存储（`name`）+ 昵称（`nickname`，外号/亲近称呼），不再拆分姓/名；代价是放弃姓氏排序与按姓称呼。
```

（第 69 行对 Monica「纯西方 first/last 结构」的批评是竞品分析历史记录，不动。）

- [ ] **Step 4: 改路线图（ROADMAP.md:40）**

```
| 联系人 | CRUD（direct/edge 双层）、中文姓名单字段模型（D23）、展示名规则、同名创建提示（D7 细化） | ✅ |
```

- [ ] **Step 5: 核对 ARCHITECTURE.md 无需改动**

spec 第 7 节列了这一项，但核对 `ARCHITECTURE.md:109` 只登记「展示名 display_name → `contacts.models.Contact.display_name` 属性」这个**实现点位置**、不写规则本身，而本次实现点未变，故不改。若 grep 发现别处写了规则描述才需要同步：

Run: `grep -n "display_name" ARCHITECTURE.md`
Expected: 只有第 109 行的实现点登记，无规则描述 → 不改

- [ ] **Step 6: 全量验证**

```bash
cd backend && uv run pytest -q && uv run ruff check .
cd ../frontend && npm run test && npm run build
```
Expected: 后端 0 failed、ruff 无输出；前端测试通过、构建产出 dist/

- [ ] **Step 7: 提交**

```bash
git add TECH_DECISIONS.md DATA_MODEL.md PROJECT_BACKGROUND.md ROADMAP.md
git commit -m "docs: 登记 D23 姓名单字段并同步数据模型/需求基线（D23）

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```
