# 活动图片 + 联系人往来 Tabs 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 活动支持多图（首图为时间线封面），联系人往来区改为三个 Tab 并按类型分页加载，三个管理列表页复用同一套表单弹窗且保存按钮带脏检查。

**Architecture:** 后端在 `app/services/storage.py` 建立唯一的文件存储原语（临时区/正式区/缩略图/路径安全），`activity_images` 表归 records 模块；图片走两阶段上传（先入临时区拿路径，表单提交时 JSON body 引用，保存时才移入正式区）。前端把活动/礼物/资金三个表单抽成共享弹窗组件，往来区改为 `el-tabs` + 每 tab 独立的无限滚动，列表页改为页码分页。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2 / Alembic / Pillow 12.3.0；Vue 3 / Element Plus / Pinia / vitest。

**Spec:** `docs/superpowers/specs/2026-09-25-activity-images-and-timeline-tabs-design.md`

## Global Constraints

- 工程规范以 `AGENTS.md` 为准：每个方法只做一个抽象层级、每个方法必须有注释（写"为什么"）、命名见名知义、TDD 先行。
- 架构规则以 `ARCHITECTURE.md` 为准：表写权独占；跨模块读只允许「调对方 service 公开函数」或「本模块 repository 只读 JOIN 对方 models」；service 是唯一业务门面；依赖单向无环。
- 权限一律经 `app/services/permission.py`（`readable_condition` / `ensure_readable` / `ensure_can_write`），禁止另写判权逻辑。
- 错误一律用 `app/core/errors.py` 的 `ValidationError`(422) / `NotFoundError`(404) / `PermissionDeniedError`(403)。
- 后端命令在 `backend/` 下：`uv run pytest`、`uv run ruff check .`（line-length 100）。前端在 `frontend/` 下：`npm run test`、`npm run build`。
- 图片格式只支持 `jpg/jpeg/png/webp`，单张 ≤10MB，每活动 ≤20 张，缩略图最长边 400px。**HEIC 不支持。**
- 列表接口分页：`limit` 默认 20、上限 200，`offset` 默认 0；**不存在"不传即全量"的旁路**。总数走 `X-Total-Count` 响应头。
- 前端视觉只消费 `frontend/src/design/tokens.ts`，禁止硬编码颜色/圆角/字体/阴影；表单弹窗统一 `el-dialog` 480px（D16/D17）。
- **不要** rebuild 镜像、不要重启测试/生产环境、不要在测试环境跑迁移（`AGENTS.md` 环境纪律）。
- 开发环境起服务用 `./dev.sh`（db 5433 + 宿主 uvicorn 8100 + Vite 5180）。

## Review Focus

以下五类输入 spec 未逐条明说、但最可能让真实用户踩坑，各自已钉到对应任务的测试里：

1. **临时路径被"认领"**：用户 A 猜到或拿到用户 B 的 `temp_path` 并塞进自己的活动提交——必须被拒（Task 5）。
2. **路径穿越**：`temp_path` 传 `../../etc/passwd` 或绝对路径——必须被拒（Task 1、Task 5）。
3. **无日期记录的排序**：礼物 `given_at`、活动 `occurred_at` 可为空，用户会以为"没填日期的记录消失了"——必须稳定排在末尾且分页不重不漏（Task 7）。
4. **筛选后停在越界页**：列表页在第 3 页时改搜索词，结果只有 1 页——必须自动回第 1 页，否则用户看到空表以为数据没了（Task 15）。
5. **取消编辑却落库**：用户改了表单又点取消/关闭，数据不该变（Task 8 的脏检查 + 各弹窗的"取消不落库"测试）。

---

## File Structure

**后端新增**
- `backend/app/services/storage.py` — 文件存储唯一实现点（L0 横切，无表）
- `backend/app/modules/uploads/__init__.py`、`api.py` — 临时区上传/读取端点（无表模块，先例：`modules/geo`）
- `backend/alembic/versions/<rev>_activity_images.py` — 迁移
- `backend/tests/test_storage.py`、`test_uploads_api.py`、`test_activity_images.py`、`test_pagination.py`

**后端修改**
- `backend/pyproject.toml`（+pillow）、`app/core/config.py`（+upload_dir）、`app/models/__init__.py`（注册新模型）
- `app/modules/records/{models,schemas,repository,service,api}.py`（图片 + contact_id + 分页）
- `app/modules/gifts/{repository,service,api}.py`、`app/modules/funds/{repository,service,api}.py`（分页）
- `app/api/v1/router.py`（挂 uploads）、`.env.example`、`../.gitignore`、`../docker-compose.yml`

**前端新增**
- `src/composables/useFormDirty.ts`、`useAuthedImage.ts`
- `src/components/{ImageUploader,ActivityFormDialog,GiftFormDialog,FundFormDialog,RecordTimeline}.vue`
- `tests/useFormDirty.spec.ts`

**前端修改**
- `src/api/{client,types,records,gifts,funds}.ts`
- `src/pages/{ActivitiesPage,GiftsPage,FundsPage,TasksPage,WishlistPage,ContactsPage,ContactDetailPage}.vue`

**文档**
- `TECH_DECISIONS.md`（D10→✅、新增 D18/D19）、`ARCHITECTURE.md`、`DATA_MODEL.md`、`DESIGN.md`

---

## Phase 1：存储地基

### Task 1: 文件存储原语与配置

**Files:**
- Create: `backend/app/services/storage.py`
- Create: `backend/tests/test_storage.py`
- Modify: `backend/pyproject.toml`（加 pillow）
- Modify: `backend/app/core/config.py`（加 upload_dir）
- Modify: `backend/.env.example`、`.gitignore`、`docker-compose.yml`

**Interfaces:**
- Consumes: `app.core.config.get_settings()`、`app.core.errors.ValidationError`
- Produces:
  - `upload_root() -> Path`（上传根目录绝对路径，不存在则创建）
  - `resolve_within_root(relative: str) -> Path`（越界抛 `ValidationError`）
  - `save_temp(user_id: int, filename: str, content: bytes) -> str`（返回 `tmp/{user_id}/{uuid}.{ext}`）
  - `promote_temp(temp_path: str, user_id: int, kind: str) -> tuple[str, str]`（返回 `(正式路径, 缩略图路径)`）
  - `delete_files(*relative_paths: str | None) -> None`
  - `defer_delete(db, *relative_paths: str | None) -> None`（登记"提交成功后删"）
  - `cleanup_temp(ttl_hours: int = 24) -> int`
  - 常量 `ALLOWED_EXTENSIONS` / `MAX_IMAGE_BYTES` / `THUMB_MAX_EDGE` / `TEMP_TTL_HOURS`

**为什么需要 `defer_delete`：** `app/core/db.py` 的 `get_db` 约定「服务层只做 flush 不做 commit，一个请求一个事务」。文件删除必须在事务**提交成功之后**——提交失败要回滚数据，此时若文件已删，DB 里就会留下指向不存在文件的坏行（比留孤儿文件难修得多）。所以 service 只登记路径，由 session 的 `after_commit` 事件真正删盘。

- [ ] **Step 1: 加 Pillow 依赖**

```bash
cd backend && uv add pillow
```
预期：`pyproject.toml` 出现 `"pillow>=12.3.0"`，`uv.lock` 更新。

- [ ] **Step 2: 加配置项**

`backend/app/core/config.py` 的 `Settings` 里，在 `jwt_expire_minutes` 之后加：

```python
    # 上传文件根目录（D18）：开发环境为 backend/uploads，容器内由 env 指向挂载卷
    upload_dir: str = "uploads"
```

`backend/.env.example` 末尾加：

```
# 上传文件目录（默认 backend/uploads；容器内由 compose 注入 /app/uploads）
UPLOAD_DIR=uploads
```

`.gitignore`（仓库根）加一行：

```
backend/uploads/
```

`docker-compose.yml`：`backend` 服务的 `environment` 加 `UPLOAD_DIR: /app/uploads`，`volumes` 加 `- uploads_data:/app/uploads`，文件末尾的 `volumes:` 段加 `uploads_data:`。

- [ ] **Step 3: 写失败测试**

`backend/tests/test_storage.py`：

```python
"""storage 模块测试：路径安全、临时区、正式区 promotion、缩略图与延迟删除。"""

import os
import time

import pytest
from PIL import Image

from app.core.config import get_settings
from app.core.errors import ValidationError
from app.services import storage


@pytest.fixture(autouse=True)
def _isolated_upload_root(tmp_path, monkeypatch):
    """把上传根目录指向临时目录，避免测试写进项目的 backend/uploads。"""
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _write_fake_image(user_id: int, name: str = "pic.jpg") -> str:
    """造一张真实的小 JPEG 放进临时区，返回其相对路径。"""
    relative = storage.save_temp(user_id, name, _jpeg_bytes())
    return relative


def _jpeg_bytes(size: tuple[int, int] = (1200, 800)) -> bytes:
    """生成一张指定尺寸的 JPEG 字节流（缩略图用例需要真实可解码的图片）。"""
    import io

    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, "JPEG")
    return buffer.getvalue()


def test_resolve_within_root_rejects_traversal():
    """含 .. 的相对路径不能逃出上传根目录。"""
    with pytest.raises(ValidationError):
        storage.resolve_within_root("../etc/passwd")


def test_resolve_within_root_rejects_absolute_path():
    """绝对路径同样拒绝，否则可读写任意系统文件。"""
    with pytest.raises(ValidationError):
        storage.resolve_within_root("/etc/passwd")


def test_save_temp_rejects_unknown_extension():
    """白名单外的扩展名拒绝（HEIC 明确不支持）。"""
    with pytest.raises(ValidationError):
        storage.save_temp(1, "photo.heic", b"x")


def test_save_temp_rejects_oversized_file():
    """超过 10MB 的单张图片拒绝。"""
    with pytest.raises(ValidationError):
        storage.save_temp(1, "big.jpg", b"x" * (storage.MAX_IMAGE_BYTES + 1))


def test_save_temp_writes_into_user_directory():
    """临时文件落在 tmp/{user_id}/ 下并返回相对路径。"""
    relative = storage.save_temp(7, "a.jpg", _jpeg_bytes((10, 10)))

    assert relative.startswith("tmp/7/")
    assert (storage.upload_root() / relative).is_file()


def test_promote_temp_rejects_other_users_temp_path():
    """不能把别人的临时文件搬进自己的正式区（认领攻击）。"""
    relative = _write_fake_image(7)

    with pytest.raises(ValidationError):
        storage.promote_temp(relative, user_id=8, kind="activities")


def test_promote_temp_rejects_missing_temp_file():
    """临时文件不存在（已过期被清理）时给出可读错误，而不是抛文件系统异常。"""
    with pytest.raises(ValidationError):
        storage.promote_temp("tmp/7/nope.jpg", user_id=7, kind="activities")


def test_promote_temp_moves_file_and_builds_thumbnail():
    """正式区拿到原图，另生成一张最长边不超过 400 的缩略图，临时文件被移走。"""
    temp_relative = _write_fake_image(7)

    full, thumb = storage.promote_temp(temp_relative, user_id=7, kind="activities")

    assert full.startswith("activities/")
    assert (storage.upload_root() / full).is_file()
    assert not (storage.upload_root() / temp_relative).exists()
    with Image.open(storage.upload_root() / thumb) as image:
        assert max(image.size) <= storage.THUMB_MAX_EDGE


def test_cleanup_temp_removes_only_expired_files():
    """清理只删超过 TTL 的孤儿临时文件，新文件保留。"""
    fresh = storage.save_temp(7, "fresh.jpg", _jpeg_bytes((10, 10)))
    stale = storage.save_temp(7, "stale.jpg", _jpeg_bytes((10, 10)))
    stale_path = storage.upload_root() / stale
    old = time.time() - (storage.TEMP_TTL_HOURS + 1) * 3600
    os.utime(stale_path, (old, old))

    removed = storage.cleanup_temp()

    assert removed == 1
    assert (storage.upload_root() / fresh).is_file()
    assert not stale_path.exists()
```

- [ ] **Step 4: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_storage.py -v
```
预期：collection error，`ImportError: cannot import name 'storage'`。

- [ ] **Step 5: 实现 storage.py**

`backend/app/services/storage.py`：

```python
"""文件存储唯一实现点（L0 横切，D18）：临时区、正式区、缩略图、路径安全。

无表无状态、不判权——配置由 core.config 注入，HTTP 与鉴权在各业务模块。
文件删除必须发生在事务提交之后，故提供 defer_delete() 登记、由 after_commit 事件真正删盘。
"""

import shutil
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationError

# 只收这四种；HEIC 是手机直出格式但需额外解码库，明确不支持
ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
MAX_IMAGE_BYTES = 10 * 1024 * 1024
THUMB_MAX_EDGE = 400
TEMP_TTL_HOURS = 24

# 会话级"提交成功后待删文件"的登记键
_PENDING_DELETE_KEY = "pending_file_deletes"


def upload_root() -> Path:
    """上传根目录的绝对路径，不存在则创建。"""
    root = Path(get_settings().upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_within_root(relative_path: str) -> Path:
    """把相对路径解析为根目录下的绝对路径；越界（.. 或绝对路径）一律拒绝。

    所有落盘操作都必须先过这里——这是防路径穿越的唯一关口。
    """
    root = upload_root()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValidationError("非法的文件路径")
    return candidate


def validate_image_extension(filename: str) -> str:
    """校验扩展名在白名单内，返回小写扩展名（含点）。"""
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed = "/".join(sorted(ALLOWED_EXTENSIONS))
        raise ValidationError(f"只支持 {allowed} 格式的图片")
    return extension


def save_temp(user_id: int, filename: str, content: bytes) -> str:
    """把上传字节写入该用户的临时区，返回相对路径。

    文件名由服务端生成（不采用客户端文件名），扩展名走白名单。
    """
    if len(content) > MAX_IMAGE_BYTES:
        raise ValidationError("单张图片不能超过 10MB")
    extension = validate_image_extension(filename)

    relative_path = f"tmp/{user_id}/{uuid.uuid4().hex}{extension}"
    target = resolve_within_root(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return relative_path


def promote_temp(temp_path: str, user_id: int, kind: str) -> tuple[str, str]:
    """把临时文件移入正式区并生成缩略图，返回 (正式路径, 缩略图路径)。

    temp_path 必须位于该用户的临时区，否则拒绝——防止把他人临时文件认领进自己的记录。
    """
    normalized = temp_path.strip().lstrip("/")
    if not normalized.startswith(f"tmp/{user_id}/"):
        raise ValidationError("非法的临时文件路径")

    source = resolve_within_root(normalized)
    if not source.is_file():
        raise ValidationError("临时文件不存在或已过期，请重新上传")

    now = datetime.now()
    stem = uuid.uuid4().hex
    relative_path = f"{kind}/{now:%Y}/{now:%m}/{stem}{source.suffix.lower()}"
    target = resolve_within_root(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))

    thumb_relative = f"{kind}/{now:%Y}/{now:%m}/{stem}.thumb.jpg"
    _write_thumbnail(target, resolve_within_root(thumb_relative))
    return relative_path, thumb_relative


def _write_thumbnail(source: Path, target: Path) -> None:
    """生成最长边不超过 THUMB_MAX_EDGE 的 JPEG 缩略图（列表卡片用，避免加载原图）。"""
    with Image.open(source) as image:
        converted = image.convert("RGB")
        converted.thumbnail((THUMB_MAX_EDGE, THUMB_MAX_EDGE))
        converted.save(target, "JPEG", quality=82)


def delete_files(*relative_paths: str | None) -> None:
    """直接删除若干文件（不存在则忽略）；调用方需自行保证时机正确。"""
    for relative_path in relative_paths:
        if not relative_path:
            continue
        try:
            resolve_within_root(relative_path).unlink(missing_ok=True)
        except ValidationError:
            continue  # 非法路径不该出现在库里；跳过而不是让清理流程崩掉


def defer_delete(db, *relative_paths: str | None) -> None:
    """登记"事务提交成功后删除"的文件（先 DB 后文件，见设计文档 3.4）。

    service 层只 flush 不 commit，所以不能在这里直接删盘：提交失败回滚时
    文件已被删，会留下指向不存在文件的坏行。真正删除由 after_commit 事件执行。
    """
    session = db.sync_session if hasattr(db, "sync_session") else db
    pending = session.info.setdefault(_PENDING_DELETE_KEY, [])
    pending.extend(path for path in relative_paths if path)


@event.listens_for(Session, "after_commit")
def _flush_deferred_deletes(session: Session) -> None:
    """提交成功后统一删除本轮登记的文件；回滚时 info 保留、文件不动。"""
    for relative_path in session.info.pop(_PENDING_DELETE_KEY, []):
        delete_files(relative_path)


def cleanup_temp(ttl_hours: int = TEMP_TTL_HOURS) -> int:
    """删除临时区中超过 ttl 小时的孤儿文件，返回删除数量（应用启动时调用一次）。"""
    temp_root = upload_root() / "tmp"
    if not temp_root.is_dir():
        return 0
    cutoff = datetime.now().timestamp() - ttl_hours * 3600
    removed = 0
    for item in temp_root.rglob("*"):
        if item.is_file() and item.stat().st_mtime < cutoff:
            item.unlink(missing_ok=True)
            removed += 1
    return removed
```

- [ ] **Step 6: 跑测试确认通过**

```bash
cd backend && uv run pytest tests/test_storage.py -v && uv run ruff check app/services/storage.py tests/test_storage.py
```
预期：全部 PASS。

- [ ] **Step 7: 提交**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/services/storage.py backend/app/core/config.py backend/tests/test_storage.py backend/.env.example .gitignore docker-compose.yml
git commit -m "feat(storage): 文件存储原语与上传配置（D18）"
```

---

### Task 2: activity_images 表与迁移

**Files:**
- Modify: `backend/app/modules/records/models.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<rev>_activity_images.py`（autogenerate 产出）
- Test: `backend/tests/test_activity_images.py`

**Interfaces:**
- Produces: `ActivityImage` 模型（`id` / `activity_id` / `path` / `thumb_path` / `sort_order` / `created_at` / `updated_at`）

**设计取舍：** 与 `ActivityParticipant` 一致，**不带 D7 三件套**——图片的可见性完全跟随活动本身，不单独判权。带 `TimestampMixin` 以便排查。

- [ ] **Step 1: 加模型**

`backend/app/modules/records/models.py` 末尾加：

```python
class ActivityImage(Base, TimestampMixin):
    """活动图片：一个活动多张图，数组顺序即展示顺序（最小 sort_order 为时间线封面）。

    不带 D7 三件套：可见性完全跟随所属活动，与 ActivityParticipant 同一取舍。
    """

    __tablename__ = "activity_images"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("activities.id", ondelete="CASCADE"),
        index=True,
        comment="所属活动",
    )
    path: Mapped[str] = mapped_column(String(500), comment="正式区相对路径")
    thumb_path: Mapped[str] = mapped_column(String(500), comment="缩略图相对路径")
    sort_order: Mapped[int] = mapped_column(Integer, index=True, comment="展示顺序，升序")
```

同时把文件头的 `Integer` 加进 sqlalchemy 导入：

```python
from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
```

- [ ] **Step 2: 注册模型**

`backend/app/models/__init__.py` 的 records 行改为：

```python
from app.modules.records.models import (  # noqa: F401
    Activity,
    ActivityImage,
    ActivityParticipant,
    Note,
    Task,
)
```

- [ ] **Step 3: 写失败测试**

`backend/tests/test_activity_images.py`：

```python
"""activity_images 表结构测试：级联删除与排序字段。"""

import pytest
from sqlalchemy import text


async def test_activity_image_table_exists(db_session):
    """迁移后表存在且含约定列。"""
    rows = await db_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'activity_images'"
        )
    )
    columns = {row[0] for row in rows}

    assert {"activity_id", "path", "thumb_path", "sort_order"} <= columns


async def test_deleting_activity_cascades_images(db_session, make_user):
    """删除活动时图片行级联删除（文件删除由 service 另行负责）。"""
    from app.modules.records.models import Activity, ActivityImage

    user, _ = await make_user("owner", "pw12345678")
    activity = Activity(title="聚会", owner_user_id=user.id, family_id=user.family_id)
    db_session.add(activity)
    await db_session.flush()
    db_session.add(
        ActivityImage(
            activity_id=activity.id, path="activities/a.jpg", thumb_path="activities/a.thumb.jpg", sort_order=0
        )
    )
    await db_session.flush()

    await db_session.execute(Activity.__table__.delete().where(Activity.id == activity.id))
    await db_session.flush()

    remaining = await db_session.execute(
        text("SELECT count(*) FROM activity_images WHERE activity_id = :aid"), {"aid": activity.id}
    )
    assert remaining.scalar_one() == 0
```

- [ ] **Step 4: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_activity_images.py -v
```
预期：FAIL，`relation "activity_images" does not exist`（conftest 用 `create_all` 建表，此时模型已加，应能通过——若失败说明模型没注册进 `app/models/__init__.py`）。

- [ ] **Step 5: 生成并检查迁移**

```bash
cd backend && uv run alembic revision --autogenerate -m "activity_images"
```
打开生成的文件确认：`op.create_table("activity_images", ...)` 含 `ondelete="CASCADE"` 的外键与 `sort_order` 索引。**检查 `down_revision` 指向当前 head**（用 `uv run alembic heads` 核对）。

- [ ] **Step 6: 跑迁移与测试**

```bash
cd backend && uv run alembic upgrade head && uv run pytest tests/test_activity_images.py -v
```
预期：迁移成功，测试 PASS。

- [ ] **Step 7: 提交**

```bash
git add backend/app/modules/records/models.py backend/app/models/__init__.py backend/alembic/versions backend/tests/test_activity_images.py
git commit -m "feat(records): activity_images 表与迁移"
```

---

### Task 3: uploads 模块（临时区上传与读取）

**Files:**
- Create: `backend/app/modules/uploads/__init__.py`
- Create: `backend/app/modules/uploads/api.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_uploads_api.py`

**Interfaces:**
- Consumes: `storage.save_temp` / `storage.resolve_within_root`（Task 1）、`get_current_user`（`app.api.deps`）、`get_db`（`app.core.db`）
- Produces:
  - `POST /api/v1/uploads/temp`（multipart 字段名 `file`）→ `{"temp_path": "tmp/1/ab.jpg"}`
  - `GET /api/v1/uploads/tmp/{user_id}/{filename}` → 图片字节流；他人一律 404

- [ ] **Step 1: 写失败测试**

`backend/tests/test_uploads_api.py`：

```python
"""uploads 端点测试：临时上传、本人可读、他人不可读。"""

import io

import pytest
from PIL import Image


def _image_upload(size: tuple[int, int] = (20, 20)) -> dict:
    """构造 multipart 上传体（真实 JPEG，避免解码失败）。"""
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, "JPEG")
    return {"file": ("pic.jpg", buffer.getvalue(), "image/jpeg")}


@pytest.fixture(autouse=True)
def _isolated_upload_root(tmp_path, monkeypatch):
    """上传根目录指向临时目录，避免污染项目 backend/uploads。"""
    from app.core.config import get_settings

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_upload_temp_returns_path(client, login_headers, make_user):
    """上传成功返回 tmp/{user_id}/ 下的相对路径。"""
    user, password = await make_user("uploader", "pw12345678")
    headers = await login_headers("uploader", "pw12345678")

    response = await client.post("/api/v1/uploads/temp", files=_image_upload(), headers=headers)

    assert response.status_code == 200
    temp_path = response.json()["temp_path"]
    assert temp_path.startswith(f"tmp/{user.id}/")


async def test_upload_temp_requires_login(client):
    """未登录不能上传。"""
    response = await client.post("/api/v1/uploads/temp", files=_image_upload())

    assert response.status_code == 401


async def test_read_own_temp_image(client, login_headers, make_user):
    """本人可以读回自己刚上传的临时图（表单预览用）。"""
    _, _ = await make_user("reader", "pw12345678")
    headers = await login_headers("reader", "pw12345678")
    temp_path = (
        await client.post("/api/v1/uploads/temp", files=_image_upload(), headers=headers)
    ).json()["temp_path"]

    response = await client.get(f"/api/v1/uploads/{temp_path}", headers=headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


async def test_read_other_users_temp_image_is_404(client, login_headers, make_user):
    """他人的临时文件一律 404（不泄露存在性）。"""
    await make_user("owner_a", "pw12345678")
    await make_user("owner_b", "pw12345678")
    headers_a = await login_headers("owner_a", "pw12345678")
    headers_b = await login_headers("owner_b", "pw12345678")
    temp_path = (
        await client.post("/api/v1/uploads/temp", files=_image_upload(), headers=headers_a)
    ).json()["temp_path"]

    response = await client.get(f"/api/v1/uploads/{temp_path}", headers=headers_b)

    assert response.status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_uploads_api.py -v
```
预期：FAIL，全部 404（路由不存在）。

- [ ] **Step 3: 实现模块**

`backend/app/modules/uploads/__init__.py`：

```python
"""uploads 模块：通用文件上传（无表，逻辑委托 app.services.storage）。"""
```

`backend/app/modules/uploads/api.py`：

```python
"""uploads 模块 API：临时区上传与本人读取。

鉴权边界：临时文件只有上传者本人能读；提交进业务记录后，改由各业务模块
（如 records 的活动图片端点）按业务可见性判权。
"""

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.errors import NotFoundError
from app.modules.auth.models import User
from app.services import storage

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("/temp")
async def upload_temp(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
) -> dict:
    """上传单张图片到当前用户的临时区，返回相对路径供表单提交时引用。"""
    content = await file.read()
    temp_path = storage.save_temp(current_user.id, file.filename or "", content)
    return {"temp_path": temp_path}


@router.get("/tmp/{user_id}/{filename}")
async def read_temp_image(
    user_id: int,
    filename: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """读取本人临时区中的图片（表单里预览未提交的图）；他人的一律 404。"""
    if user_id != current_user.id:
        raise NotFoundError("文件不存在")
    path = storage.resolve_within_root(f"tmp/{user_id}/{filename}")
    if not path.is_file():
        raise NotFoundError("文件不存在")
    return FileResponse(path)
```

`backend/app/api/v1/router.py`：导入并挂载

```python
from app.modules.uploads.api import router as uploads_router
...
api_v1_router.include_router(uploads_router)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && uv run pytest tests/test_uploads_api.py -v && uv run ruff check app/modules/uploads app/api/v1/router.py
```
预期：PASS。（若 `read_temp_image` 返回 404 而非 200，检查上传根目录 fixture 是否生效——`get_settings` 是 `lru_cache`，必须 `cache_clear()`。）

- [ ] **Step 5: 提交**

```bash
git add backend/app/modules/uploads backend/app/api/v1/router.py backend/tests/test_uploads_api.py
git commit -m "feat(uploads): 临时区上传与本人读取端点"
```

---

### Task 4: 活动图片的鉴权读取端点

**Files:**
- Modify: `backend/app/modules/records/api.py`
- Modify: `backend/app/modules/records/repository.py`
- Test: `backend/tests/test_activity_images.py`（追加）

**Interfaces:**
- Consumes: `records_repo.get_readable_activity`、`storage.resolve_within_root`
- Produces: `GET /api/v1/records/activities/images/{image_id}?size=thumb|full` → 图片字节流；不可见 404

**注意路由顺序**：`/activities/images/{image_id}` 必须注册在 `/activities/{activity_id}` **之前**，否则 `images` 会被当成 `activity_id` 解析而 422。

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_activity_images.py`：

```python
import io

from PIL import Image

from app.services import storage


@pytest.fixture(autouse=True)
def _isolated_upload_root(tmp_path, monkeypatch):
    """上传根目录指向临时目录。"""
    from app.core.config import get_settings

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _jpeg_bytes() -> bytes:
    """造一张可解码的 JPEG。"""
    buffer = io.BytesIO()
    Image.new("RGB", (1200, 800), "white").save(buffer, "JPEG")
    return buffer.getvalue()


async def _make_activity_with_image(db, user, visibility: str = "family"):
    """造一个带图的活动，返回 (activity_id, image_id)。图片走真实 promote 流程。"""
    from app.modules.records.models import Activity, ActivityImage

    temp_path = storage.save_temp(user.id, "p.jpg", _jpeg_bytes())
    full, thumb = storage.promote_temp(temp_path, user_id=user.id, kind="activities")
    activity = Activity(
        title="带图活动", owner_user_id=user.id, family_id=user.family_id, visibility=visibility
    )
    db.add(activity)
    await db.flush()
    image = ActivityImage(
        activity_id=activity.id, path=full, thumb_path=thumb, sort_order=0
    )
    db.add(image)
    await db.flush()
    return activity.id, image.id


async def test_read_activity_image_as_owner(client, login_headers, make_user, db_session):
    """所有者能读到活动图片。"""
    user, _ = await make_user("img_owner", "pw12345678")
    headers = await login_headers("img_owner", "pw12345678")
    _, image_id = await _make_activity_with_image(db_session, user)

    response = await client.get(f"/api/v1/records/activities/images/{image_id}", headers=headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


async def test_read_thumbnail_variant(client, login_headers, make_user, db_session):
    """size=thumb 返回缩略图（体积小于原图）。"""
    user, _ = await make_user("thumb_owner", "pw12345678")
    headers = await login_headers("thumb_owner", "pw12345678")
    _, image_id = await _make_activity_with_image(db_session, user)

    full = await client.get(f"/api/v1/records/activities/images/{image_id}", headers=headers)
    thumb = await client.get(
        f"/api/v1/records/activities/images/{image_id}?size=thumb", headers=headers
    )

    assert thumb.status_code == 200
    assert len(thumb.content) < len(full.content)


async def test_read_private_activity_image_by_other_user_is_404(
    client, login_headers, make_user, db_session
):
    """他人私有活动的图片按 404 处理，不泄露存在性。"""
    owner, _ = await make_user("priv_owner", "pw12345678")
    await make_user("priv_other", "pw12345678")
    headers = await login_headers("priv_other", "pw12345678")
    _, image_id = await _make_activity_with_image(db_session, owner, visibility="private")

    response = await client.get(f"/api/v1/records/activities/images/{image_id}", headers=headers)

    assert response.status_code == 404


async def test_activities_route_does_not_shadow_images_route(client, login_headers, make_user, db_session):
    """确认 /activities/images/{id} 没被 /activities/{id} 抢先匹配（否则 422）。"""
    user, _ = await make_user("route_owner", "pw12345678")
    headers = await login_headers("route_owner", "pw12345678")
    _, image_id = await _make_activity_with_image(db_session, user)

    response = await client.get(f"/api/v1/records/activities/images/{image_id}", headers=headers)

    assert response.status_code != 422
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_activity_images.py -v
```
预期：新增用例 FAIL（404 或 422）。

- [ ] **Step 3: 实现**

`backend/app/modules/records/repository.py` 加：

```python
async def get_image(db: AsyncSession, image_id: int) -> ActivityImage | None:
    """按 id 取图片行（不含判权；判权由 service 依所属活动完成）。"""
    stmt = select(ActivityImage).where(ActivityImage.id == image_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_images(db: AsyncSession, activity_id: int) -> list[ActivityImage]:
    """取活动的全部图片，按展示顺序升序。"""
    stmt = (
        select(ActivityImage)
        .where(ActivityImage.activity_id == activity_id)
        .order_by(ActivityImage.sort_order, ActivityImage.id)
    )
    return list((await db.execute(stmt)).scalars().all())
```

（文件头导入加 `ActivityImage`。）

`backend/app/modules/records/service.py` 加：

```python
async def get_activity_image_path(
    db: AsyncSession, user: User, image_id: int, *, thumb: bool
) -> str:
    """取活动图片的相对路径；图片所属活动不可读时按 404 处理。

    返回相对路径而不是绝对路径，落盘细节留给 api 层经 storage 解析。
    """
    image = await records_repo.get_image(db, image_id)
    if image is None:
        raise NotFoundError("图片不存在")
    activity = await records_repo.get_readable_activity(db, image.activity_id)
    if activity is None:
        raise NotFoundError("图片不存在")
    return image.thumb_path if thumb else image.path
```

`backend/app/modules/records/api.py` 加（**放在 `/activities/{activity_id}` 路由之前**）：

```python
from fastapi.responses import FileResponse
from app.core.errors import NotFoundError
from app.services import storage


@router.get("/activities/images/{image_id}")
async def read_activity_image(
    image_id: int,
    size: str = Query(default="full", description="thumb/full"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """按活动可见性鉴权后返回图片文件（登录态访问，不做静态挂载）。"""
    relative = await records_service.get_activity_image_path(
        db, current_user, image_id, thumb=(size == "thumb")
    )
    path = storage.resolve_within_root(relative)
    if not path.is_file():
        raise NotFoundError("图片不存在")
    return FileResponse(path)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && uv run pytest tests/test_activity_images.py -v && uv run ruff check app/modules/records
```
预期：PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/modules/records backend/tests/test_activity_images.py
git commit -m "feat(records): 活动图片鉴权读取端点"
```

---

### Task 5: 活动 CRUD 集成图片（全量替换语义）

**Files:**
- Modify: `backend/app/modules/records/schemas.py`
- Modify: `backend/app/modules/records/repository.py`
- Modify: `backend/app/modules/records/service.py`
- Modify: `backend/app/services/storage.py`（加纯校验函数）
- Test: `backend/tests/test_activity_images.py`（追加）

**Interfaces:**
- Consumes: `storage.promote_temp` / `storage.defer_delete` / `storage.is_own_temp_path`、`records_repo.list_images` / `get_image` / `get_readable_activity`
- Produces:
  - 请求体 `images: [{"id": 12} | {"temp_path": "tmp/1/a.jpg"}]`，**数组顺序即展示顺序**
  - 响应体 `ActivityOut.images: [{id, sort_order}]`
  - `storage.is_own_temp_path(temp_path: str, user_id: int) -> bool`

**语义：** 数组里没有的旧图 → 删除（含文件）。这是**全量替换**，与项目里 `participant_ids` 的既有约定一致，也让"第一张当封面"天然可用。

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_activity_images.py`：

```python
async def test_create_activity_with_images(client, login_headers, make_user):
    """新建活动带两张临时图：顺序即 sort_order，首张为封面。"""
    user, _ = await make_user("creator", "pw12345678")
    headers = await login_headers("creator", "pw12345678")
    first = (
        await client.post("/api/v1/uploads/temp", files=_upload("a.jpg"), headers=headers)
    ).json()["temp_path"]
    second = (
        await client.post("/api/v1/uploads/temp", files=_upload("b.jpg"), headers=headers)
    ).json()["temp_path"]

    response = await client.post(
        "/api/v1/records/activities",
        json={
            "title": "春游",
            "images": [{"temp_path": first}, {"temp_path": second}],
        },
        headers=headers,
    )

    assert response.status_code == 200
    images = response.json()["images"]
    assert [image["sort_order"] for image in images] == [0, 1]
    # 临时文件已移入正式区
    assert not (storage.upload_root() / first).exists()


def _upload(name: str) -> dict:
    """构造一张可解码图片的 multipart 体。"""
    return {"file": (name, _jpeg_bytes(), "image/jpeg")}


async def test_create_activity_rejects_other_users_temp_path(client, login_headers, make_user):
    """把别人的临时图认领进自己的活动必须被拒（Review Focus #1）。"""
    await make_user("victim", "pw12345678")
    await make_user("attacker", "pw12345678")
    victim_headers = await login_headers("victim", "pw12345678")
    attacker_headers = await login_headers("attacker", "pw12345678")
    stolen = (
        await client.post("/api/v1/uploads/temp", files=_upload("v.jpg"), headers=victim_headers)
    ).json()["temp_path"]

    response = await client.post(
        "/api/v1/records/activities",
        json={"title": "偷图", "images": [{"temp_path": stolen}]},
        headers=attacker_headers,
    )

    assert response.status_code == 422
    assert "临时" in response.json()["message"]


async def test_create_activity_rejects_traversal_temp_path(client, login_headers, make_user):
    """temp_path 里带 .. 必须被拒（Review Focus #2）。"""
    await make_user("walker", "pw12345678")
    headers = await login_headers("walker", "pw12345678")

    response = await client.post(
        "/api/v1/records/activities",
        json={"title": "穿越", "images": [{"temp_path": "tmp/1/../../etc/passwd"}]},
        headers=headers,
    )

    assert response.status_code == 422


async def test_activity_rejects_more_than_20_images(client, login_headers, make_user):
    """每活动最多 20 张。"""
    _, _ = await make_user("many", "pw12345678")
    headers = await login_headers("many", "pw12345678")

    response = await client.post(
        "/api/v1/records/activities",
        json={"title": "太多", "images": [{"id": i} for i in range(21)]},
        headers=headers,
    )

    assert response.status_code == 422


async def test_update_activity_replaces_images_wholesale(client, login_headers, make_user):
    """编辑时全量替换：保留一项、删掉未出现的旧图，顺序按提交数组重排。"""
    _, _ = await make_user("editor", "pw12345678")
    headers = await login_headers("editor", "pw12345678")
    created = (
        await client.post(
            "/api/v1/records/activities",
            json={
                "title": "原活动",
                "images": [
                    {"temp_path": _temp(headers, "1.jpg")},
                    {"temp_path": _temp(headers, "2.jpg")},
                ],
            },
            headers=headers,
        )
    ).json()
    first_id, second_id = (image["id"] for image in created["images"])

    updated = await client.patch(
        f"/api/v1/records/activities/{created['id']}",
        json={"images": [{"id": second_id}, {"temp_path": _temp(headers, "3.jpg")}]},
        headers=headers,
    )

    assert updated.status_code == 200
    images = updated.json()["images"]
    assert [image["id"] for image in images][0] == second_id
    assert first_id not in [image["id"] for image in images]


async def _temp(headers: dict, name: str) -> str:
    """上传一张临时图并返回其路径（测试助手）。"""
    raise NotImplementedError
```

**注意：** 上面最后那个 `_temp` 助手是占位写法，实施时改为模块级 async helper（`client` 需传入）：

```python
async def _temp_path(client, headers: dict, name: str) -> str:
    """上传一张临时图并返回其路径。"""
    response = await client.post(
        "/api/v1/uploads/temp", files=_upload(name), headers=headers
    )
    return response.json()["temp_path"]
```

并把 `test_update_activity_replaces_images_wholesale` 里的 `_temp(headers, "1.jpg")` 全部替换为 `await _temp_path(client, headers, "1.jpg")`。

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_activity_images.py -v
```
预期：新增用例 FAIL（images 字段被忽略或 422 schema 错误）。

- [ ] **Step 3: 加纯校验函数**

`backend/app/services/storage.py` 加（并让 `promote_temp` 复用它，保持单一实现）：

```python
def is_own_temp_path(temp_path: str, user_id: int) -> bool:
    """判断路径是否位于该用户的临时区（纯字符串校验，不落盘）。"""
    return temp_path.strip().lstrip("/").startswith(f"tmp/{user_id}/")
```

`promote_temp` 的第一个判断改为：

```python
    if not is_own_temp_path(temp_path, user_id):
        raise ValidationError("非法的临时文件路径")
```

- [ ] **Step 4: 扩展 schemas**

`backend/app/modules/records/schemas.py`：

```python
# 每个活动的图片上限：家庭相册量级足够，同时防御超长列表
MAX_IMAGES = 20


class ImageRefIn(BaseModel):
    """图片提交项：保留已有图给 id，新增图给 temp_path；数组顺序即展示顺序。"""

    id: int | None = None
    temp_path: str | None = None

    @model_validator(mode="after")
    def validate_exactly_one(self) -> "ImageRefIn":
        """id 与 temp_path 必须恰好提供一个，消除"两个都给"的歧义。"""
        if (self.id is None) == (self.temp_path is None):
            raise ValueError("图片项必须且只能给 id 或 temp_path 之一")
        return self


class ActivityImageOut(BaseModel):
    """活动图片输出：前端拿 id 拼鉴权读取地址，按 sort_order 升序展示。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sort_order: int
```

`ActivityCreate` 加字段：

```python
    images: list[ImageRefIn] = Field(default_factory=list, max_length=MAX_IMAGES)
```

`ActivityUpdate` 加字段：

```python
    images: list[ImageRefIn] | None = Field(default=None, max_length=MAX_IMAGES)
```

`ActivityOut` 加字段：

```python
    images: list[ActivityImageOut] = []
```

- [ ] **Step 5: 扩展 repository**

`backend/app/modules/records/repository.py` 加：

```python
async def list_images_for_activities(
    db: AsyncSession, activity_ids: list[int]
) -> dict[int, list[ActivityImage]]:
    """批量取多个活动的图片并按活动分组（列表接口避免 N+1 查询）。"""
    if not activity_ids:
        return {}
    stmt = (
        select(ActivityImage)
        .where(ActivityImage.activity_id.in_(activity_ids))
        .order_by(ActivityImage.sort_order, ActivityImage.id)
    )
    grouped: dict[int, list[ActivityImage]] = {}
    for image in (await db.execute(stmt)).scalars().all():
        grouped.setdefault(image.activity_id, []).append(image)
    return grouped
```

- [ ] **Step 6: 扩展 service**

`backend/app/modules/records/service.py`：

`_activity_to_out` 加图片参数：

```python
def _activity_to_out(
    activity: Activity,
    owner_display_name: str,
    participant_ids: list[int],
    images: list[ActivityImage],
) -> ActivityOut:
    """组装活动输出契约：参与者与图片均由调用方按可读性/顺序查好后传入。"""
    activity.owner_display_name = owner_display_name
    payload = ActivityOut.model_validate(activity)
    payload.participant_ids = participant_ids
    payload.images = [ActivityImageOut.model_validate(image) for image in images]
    return payload
```

新增图片落库编排（**两阶段：先纯校验，再落盘**，避免校验失败时已发生文件副作用）：

```python
async def _replace_images(
    db: AsyncSession, user: User, activity_id: int, refs: list[ImageRefIn]
) -> list[ActivityImage]:
    """按全量替换语义落图片：refs 顺序即 sort_order，未出现的旧图连同文件删除。

    先做全部纯校验再动盘：否则中途发现非法项时，前面的临时文件已被移走。
    """
    existing = {image.id: image for image in await records_repo.list_images(db, activity_id)}

    # 阶段一：纯校验
    for ref in refs:
        if ref.id is not None and ref.id not in existing:
            raise ValidationError("存在不属于本活动的图片")
        if ref.temp_path is not None and not storage.is_own_temp_path(ref.temp_path, user.id):
            raise ValidationError("非法的临时文件路径")

    # 阶段二：写新图、重排保留图
    kept_ids: set[int] = set()
    for order, ref in enumerate(refs):
        if ref.id is not None:
            existing[ref.id].sort_order = order
            kept_ids.add(ref.id)
        else:
            full_path, thumb_path = storage.promote_temp(ref.temp_path, user.id, "activities")
            db.add(
                ActivityImage(
                    activity_id=activity_id,
                    path=full_path,
                    thumb_path=thumb_path,
                    sort_order=order,
                )
            )

    # 阶段三：删除未保留的旧图（文件延迟到提交成功后删，见 storage.defer_delete）
    removed_paths: list[str] = []
    for image_id, image in existing.items():
        if image_id in kept_ids:
            continue
        removed_paths.extend([image.path, image.thumb_path])
        await db.delete(image)
    storage.defer_delete(db, *removed_paths)

    await db.flush()
    return await records_repo.list_images(db, activity_id)
```

`create_activity` 在 `replace_participants` 之后接：

```python
    images = await _replace_images(db, user, activity.id, data.images)
    return _activity_to_out(activity, user.display_name, data.participant_ids, images)
```

`update_activity` 在参与者处理之后接：

```python
    if data.images is not None:
        await _replace_images(db, user, activity.id, data.images)

    images = await records_repo.list_images(db, activity.id)
    ids = await records_repo.list_participant_ids(db, user, activity.id)
    return _activity_to_out(activity, user.display_name, ids, images)
```

`delete_activity` 改为（登记待删文件后再删行）：

```python
async def delete_activity(db: AsyncSession, user: User, activity_id: int) -> None:
    """删除活动（仅所有者）；图片行随级联删除，文件在提交成功后删。"""
    activity = await records_repo.get_readable_activity(db, user, activity_id)
    if activity is None:
        raise NotFoundError("活动不存在")
    ensure_can_write(user, activity)

    images = await records_repo.list_images(db, activity_id)
    storage.defer_delete(
        db, *[path for image in images for path in (image.path, image.thumb_path)]
    )
    await db.delete(activity)
    await db.flush()
```

其余三个读取路径（`list_activities` / `list_upcoming_activities` / `list_contact_activities` / `get_activity`）改用批量查图：

```python
async def list_activities(
    db: AsyncSession, user: User, *, search: str | None
) -> list[ActivityOut]:
    """列出可读活动，参与者与图片均按查看者可读性/顺序回显。"""
    rows = await records_repo.find_readable_activities(db, user, search=search)
    images_map = await records_repo.list_images_for_activities(
        db, [activity.id for activity, _ in rows]
    )
    outputs: list[ActivityOut] = []
    for activity, owner_name in rows:
        ids = await records_repo.list_participant_ids(db, user, activity.id)
        outputs.append(
            _activity_to_out(activity, owner_name, ids, images_map.get(activity.id, []))
        )
    return outputs
```

（`list_upcoming_activities` / `list_contact_activities` / `get_activity` 同样处理。）

- [ ] **Step 7: 跑测试确认通过**

```bash
cd backend && uv run pytest -v && uv run ruff check .
```
预期：新用例 PASS，**既有 records/ai/dashboard 测试仍全绿**（`_activity_to_out` 签名变了，确保所有调用点都改了）。

- [ ] **Step 8: 提交**

```bash
git add backend/app/modules/records backend/app/services/storage.py backend/tests/test_activity_images.py
git commit -m "feat(records): 活动图片全量替换与文件清理"
```

---

### Task 6: 活动列表支持按联系人过滤

**Files:**
- Modify: `backend/app/modules/records/repository.py`
- Modify: `backend/app/modules/records/service.py`
- Modify: `backend/app/modules/records/api.py`
- Test: `backend/tests/test_records.py`（追加）

**Interfaces:**
- Produces: `GET /api/v1/records/activities?contact_id=N`（gifts/funds 早有此参数，本次补齐第三个）

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_records.py`：

```python
async def test_list_activities_filters_by_contact(client, login_headers, make_user, db_session):
    """按 contact_id 过滤只返回该联系人作为参与者的活动。"""
    from app.modules.contacts.models import Contact
    from app.modules.records.models import Activity, ActivityParticipant

    user, _ = await make_user("filter_user", "pw12345678")
    headers = await login_headers("filter_user", "pw12345678")
    dad = Contact(
        last_name="陈", first_name="爸", owner_user_id=user.id, family_id=user.family_id
    )
    mom = Contact(
        last_name="李", first_name="妈", owner_user_id=user.id, family_id=user.family_id
    )
    db_session.add_all([dad, mom])
    await db_session.flush()
    with_dad = Activity(title="陪爸钓鱼", owner_user_id=user.id, family_id=user.family_id)
    with_mom = Activity(title="陪妈买菜", owner_user_id=user.id, family_id=user.family_id)
    db_session.add_all([with_dad, with_mom])
    await db_session.flush()
    db_session.add_all(
        [
            ActivityParticipant(activity_id=with_dad.id, contact_id=dad.id),
            ActivityParticipant(activity_id=with_mom.id, contact_id=mom.id),
        ]
    )
    await db_session.flush()

    response = await client.get(
        f"/api/v1/records/activities?contact_id={dad.id}", headers=headers
    )

    assert response.status_code == 200
    titles = [item["title"] for item in response.json()]
    assert titles == ["陪爸钓鱼"]
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_records.py::test_list_activities_filters_by_contact -v
```
预期：FAIL，返回两条（参数被忽略）。

- [ ] **Step 3: 实现**

`repository.py` 的 `find_readable_activities` 加 `contact_id` 参数（复用既有 `ActivityParticipant` join）：

```python
async def find_readable_activities(
    db: AsyncSession,
    user,
    *,
    search: str | None = None,
    from_time: datetime | None = None,
    contact_id: int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[tuple[Activity, str]]:
    """按读取范围查活动列表，返回 (活动, 所有者展示名) 行。

    search 模糊匹配标题与地点；from_time 只取该时刻之后的活动（待办聚合用）；
    contact_id 只取该联系人作为参与者的活动（联系人往来 Tab 用）。
    """
    stmt = (
        select(Activity, User.display_name.label("owner_display_name"))
        .join(User, User.id == Activity.owner_user_id)
        .where(Activity.is_active.is_(True), readable_condition(Activity, user))
    )
    if contact_id is not None:
        stmt = stmt.join(
            ActivityParticipant, ActivityParticipant.activity_id == Activity.id
        ).where(ActivityParticipant.contact_id == contact_id)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(Activity.title.ilike(pattern) | Activity.location.ilike(pattern))
    if from_time is not None:
        stmt = stmt.where(Activity.occurred_at >= from_time)
    stmt = stmt.order_by(Activity.occurred_at.desc().nulls_last(), Activity.id.desc())
    if limit is not None:
        stmt = stmt.limit(limit).offset(offset)
    return list((await db.execute(stmt)).all())
```

`service.py` 的 `list_activities` 加参数并透传（同时按 Task 5 的方式补 images）：

```python
async def list_activities(
    db: AsyncSession,
    user: User,
    *,
    search: str | None,
    contact_id: int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[ActivityOut]:
    """列出可读活动；contact_id 用于联系人往来 Tab，limit/offset 用于分页。"""
    rows = await records_repo.find_readable_activities(
        db, user, search=search, contact_id=contact_id, limit=limit, offset=offset
    )
    images_map = await records_repo.list_images_for_activities(
        db, [activity.id for activity, _ in rows]
    )
    outputs: list[ActivityOut] = []
    for activity, owner_name in rows:
        ids = await records_repo.list_participant_ids(db, user, activity.id)
        outputs.append(
            _activity_to_out(activity, owner_name, ids, images_map.get(activity.id, []))
        )
    return outputs
```

`api.py` 的 `list_activities` 加参数：

```python
@router.get("/activities", response_model=list[ActivityOut])
async def list_activities(
    search: str | None = None,
    contact_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ActivityOut]:
    """活动列表（新→旧），支持标题/地点搜索与按参与者联系人过滤。"""
    return await records_service.list_activities(
        db, current_user, search=search, contact_id=contact_id
    )
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && uv run pytest tests/test_records.py -v
```
预期：PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/modules/records backend/tests/test_records.py
git commit -m "feat(records): 活动列表支持按联系人过滤"
```

---

### Task 7: 三个列表接口分页与总数头

**Files:**
- Modify: `backend/app/modules/{records,gifts,funds}/repository.py`、`service.py`、`api.py`
- Test: `backend/tests/test_pagination.py`

**Interfaces:**
- Produces: 三个 list 端点统一支持 `?limit=`（默认 20，`ge=1, le=200`）与 `?offset=`（默认 0，`ge=0`），响应头 `X-Total-Count`（总是返回）
- 新增 service 函数：`count_activities` / `count_gifts` / `count_fund_flows`（签名与各自 `list_*` 的过滤参数一致，但不含 limit/offset）

**为什么默认 20 而不是"不传即全量"：** 用户 2026-09-25 明确要求保守默认，避免任何调用方无意间拉全表。该默认只作用于 HTTP 层，service 的 `limit=None` 仍表示不分页，故 AI 工具与主页聚合不受影响。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_pagination.py`：

```python
"""分页契约测试：默认 20、上限截断、offset 翻页、总数头。"""

import pytest

PAGED_ENDPOINTS = [
    "/api/v1/records/activities",
    "/api/v1/gifts",
    "/api/v1/funds",
]


async def _seed_activities(db, user, count: int) -> None:
    """造 count 条活动，标题带序号便于断言顺序。"""
    from app.modules.records.models import Activity

    for index in range(count):
        db.add(
            Activity(
                title=f"活动{index:02d}",
                owner_user_id=user.id,
                family_id=user.family_id,
            )
        )
    await db.flush()


@pytest.mark.parametrize("endpoint", PAGED_ENDPOINTS)
async def test_pagination_defaults_to_20(endpoint, client, login_headers, make_user, db_session):
    """不传 limit 时最多返回 20 条（不存在"不传即全量"的旁路）。"""
    user, _ = await make_user("pager", "pw12345678")
    headers = await login_headers("pager", "pw12345678")
    await _seed_activities(db_session, user, 25)

    response = await client.get(endpoint, headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 20


@pytest.mark.parametrize("endpoint", PAGED_ENDPOINTS)
async def test_pagination_returns_total_count(endpoint, client, login_headers, make_user, db_session):
    """X-Total-Count 反映的是总数而非本页条数（列表页页码要靠它算）。"""
    user, _ = await make_user("counter", "pw12345678")
    headers = await login_headers("counter", "pw12345678")
    await _seed_activities(db_session, user, 25)

    response = await client.get(endpoint, headers=headers)

    assert response.headers["X-Total-Count"] == "25"


@pytest.mark.parametrize("endpoint", PAGED_ENDPOINTS)
async def test_pagination_limit_is_capped(endpoint, client, login_headers, make_user, db_session):
    """limit 超过 200 被拒（防 limit=999999 绕过保护）。"""
    await make_user("capper", "pw12345678")
    headers = await login_headers("capper", "pw12345678")

    response = await client.get(f"{endpoint}?limit=999999", headers=headers)

    assert response.status_code == 422


async def test_offset_pages_do_not_overlap(client, login_headers, make_user, db_session):
    """offset 翻页不重不漏（无日期记录稳定排末尾，见 Review Focus #3）。"""
    user, _ = await make_user("pager2", "pw12345678")
    headers = await login_headers("pager2", "pw12345678")
    await _seed_activities(db_session, user, 25)

    first = (
        await client.get("/api/v1/records/activities?limit=20&offset=0", headers=headers)
    ).json()
    second = (
        await client.get("/api/v1/records/activities?limit=20&offset=20", headers=headers)
    ).json()

    first_ids = {item["id"] for item in first}
    second_ids = {item["id"] for item in second}
    assert len(first_ids & second_ids) == 0
    assert len(first_ids | second_ids) == 25
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_pagination.py -v
```
预期：FAIL（默认返回全部 25 条、无 `X-Total-Count` 头、`limit=999999` 不报错）。

- [ ] **Step 3: 实现（三个模块同一套改法）**

**repository 层**——每个 `find_readable_*` 加 `limit: int | None = None, offset: int = 0`，并在 `order_by` 之后：

```python
    if limit is not None:
        stmt = stmt.limit(limit).offset(offset)
```

并各加一个计数函数（**过滤条件必须与对应 find 完全一致**，否则总数和列表对不上）：

```python
async def count_readable_activities(
    db: AsyncSession, user, *, search: str | None = None, contact_id: int | None = None
) -> int:
    """统计可读活动总数（过滤条件与 find_readable_activities 保持一致）。"""
    stmt = select(func.count()).select_from(Activity).where(
        Activity.is_active.is_(True), readable_condition(Activity, user)
    )
    if contact_id is not None:
        stmt = stmt.join(
            ActivityParticipant, ActivityParticipant.activity_id == Activity.id
        ).where(ActivityParticipant.contact_id == contact_id)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(Activity.title.ilike(pattern) | Activity.location.ilike(pattern))
    return (await db.execute(stmt)).scalar_one()
```

（gifts / funds 同理，过滤条件照抄各自 `find_readable_*`；文件头补 `from sqlalchemy import func`。）

**service 层**——`list_*` 加 `limit` / `offset` 参数透传，并各加：

```python
async def count_activities(
    db: AsyncSession, user: User, *, search: str | None, contact_id: int | None = None
) -> int:
    """活动总数（分页头 X-Total-Count 用）。"""
    return await records_repo.count_readable_activities(
        db, user, search=search, contact_id=contact_id
    )
```

**api 层**——三个端点加 `Response` 注入、query 参数与响应头：

```python
@router.get("/activities", response_model=list[ActivityOut])
async def list_activities(
    response: Response,
    search: str | None = None,
    contact_id: int | None = None,
    limit: int = Query(default=20, ge=1, le=200, description="每页条数（上限 200）"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ActivityOut]:
    """活动列表（新→旧）；总数走 X-Total-Count 头，供列表页算页码。"""
    total = await records_service.count_activities(
        db, current_user, search=search, contact_id=contact_id
    )
    response.headers["X-Total-Count"] = str(total)
    return await records_service.list_activities(
        db, current_user, search=search, contact_id=contact_id, limit=limit, offset=offset
    )
```

- [ ] **Step 4: 跑全量测试**

```bash
cd backend && uv run pytest -v && uv run ruff check .
```
预期：新测试 PASS；**既有列表页相关测试若断言"返回全部"会失败**——那些测试应改成显式传 `limit`，属于预期内的契约变更。逐个修改并重跑，直到全绿。

- [ ] **Step 5: 提交**

```bash
git add backend/app/modules/records backend/app/modules/gifts backend/app/modules/funds backend/tests
git commit -m "feat(api): 三个列表接口分页与 X-Total-Count"
```

---

## Phase 4：前端基础件

### Task 8: useFormDirty（保存按钮唯一脏检查实现点）

**Files:**
- Create: `frontend/src/composables/useFormDirty.ts`
- Create: `frontend/tests/useFormDirty.spec.ts`

**Interfaces:**
- Produces: `useFormDirty<T>(current: Ref<T>, options?: { isSubmittable?: (value: T) => boolean })` → `{ capture, isDirty, canSubmit }`
  - `capture()`：把当前值记为基线（打开弹窗时调用）
  - `isDirty: ComputedRef<boolean>`：相对基线是否有改动
  - `canSubmit: ComputedRef<boolean>`：`isDirty && isSubmittable(值)`

- [ ] **Step 1: 写失败测试**

`frontend/tests/useFormDirty.spec.ts`：

```ts
/** 脏检查测试：保存按钮的行为契约（用户 2026-09-25 指令）。 */
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { useFormDirty } from '@/composables/useFormDirty'

describe('useFormDirty', () => {
  it('刚打开时无改动，保存不可点', () => {
    const form = ref({ title: '原标题', amount: '100' })
    const dirty = useFormDirty(form)

    dirty.capture()

    expect(dirty.isDirty.value).toBe(false)
    expect(dirty.canSubmit.value).toBe(false)
  })

  it('改了内容就可保存', () => {
    const form = ref({ title: '原标题' })
    const dirty = useFormDirty(form)
    dirty.capture()

    form.value.title = '新标题'

    expect(dirty.isDirty.value).toBe(true)
    expect(dirty.canSubmit.value).toBe(true)
  })

  it('改完又改回原值，保存重新变灰', () => {
    const form = ref({ title: '原标题' })
    const dirty = useFormDirty(form)
    dirty.capture()

    form.value.title = '改了'
    form.value.title = '原标题'

    expect(dirty.canSubmit.value).toBe(false)
  })

  it('有改动但必填项为空时仍然不可保存', () => {
    const form = ref({ title: '原标题' })
    const dirty = useFormDirty(form, {
      isSubmittable: (value) => value.title.trim().length > 0,
    })
    dirty.capture()

    form.value.title = '   '

    expect(dirty.isDirty.value).toBe(true)
    expect(dirty.canSubmit.value).toBe(false)
  })

  it('新建态（空表单为基线）：填了必填项才可保存', () => {
    const form = ref({ title: '' })
    const dirty = useFormDirty(form, {
      isSubmittable: (value) => value.title.trim().length > 0,
    })
    dirty.capture()

    expect(dirty.canSubmit.value).toBe(false)

    form.value.title = '家庭聚餐'

    expect(dirty.canSubmit.value).toBe(true)
  })

  it('数组增删算改动', () => {
    const form = ref({ ids: [1, 2] })
    const dirty = useFormDirty(form)
    dirty.capture()

    form.value.ids.push(3)
    expect(dirty.isDirty.value).toBe(true)

    form.value.ids.pop()
    expect(dirty.isDirty.value).toBe(false)
  })

  it('对象 key 顺序不同但内容相同不算改动', () => {
    const form = ref<Record<string, unknown>>({ alpha: 1, beta: 2 })
    const dirty = useFormDirty(form)
    dirty.capture()

    form.value = { beta: 2, alpha: 1 }

    expect(dirty.isDirty.value).toBe(false)
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npm run test -- tests/useFormDirty.spec.ts
```
预期：FAIL，`useFormDirty` 不存在。

- [ ] **Step 3: 实现**

`frontend/src/composables/useFormDirty.ts`：

```ts
/**
 * 表单脏检查（全站唯一实现点）：
 * 只有「相对打开时的快照有改动」且「附加校验通过」才允许保存。
 *
 * 目的是防误操作——用户改完表单直接关闭不落库，只有真的改了并点保存才写入。
 * 新建场景把空表单当基线，因此「填了必填项」天然等于「有改动」，无需分支处理。
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'

interface FormDirtyOptions<T> {
  /** 附加可用性校验（如必填项非空）；返回 false 时即便有改动也不可保存。 */
  isSubmittable?: (value: T) => boolean
}

interface FormDirty<T> {
  /** 把当前值记为基线；打开弹窗/载入数据后调用。 */
  capture: () => void
  /** 相对基线是否有改动。 */
  isDirty: ComputedRef<boolean>
  /** 保存按钮是否可用。 */
  canSubmit: ComputedRef<boolean>
}

/**
 * 稳定序列化：对象按 key 排序后序列化。
 * 否则 `{a:1,b:2}` 与 `{b:2,a:1}` 会被判成有改动（表单回填重建对象时很常见）。
 */
function stableSerialize(value: unknown): string {
  return JSON.stringify(value, (_key, val: unknown) => {
    if (val && typeof val === 'object' && !Array.isArray(val)) {
      return Object.fromEntries(
        Object.entries(val as Record<string, unknown>).sort(([left], [right]) =>
          left.localeCompare(right),
        ),
      )
    }
    return val
  })
}

export function useFormDirty<T>(current: Ref<T>, options: FormDirtyOptions<T> = {}): FormDirty<T> {
  const baseline = ref<string>('')

  /** 记录基线快照。 */
  function capture(): void {
    baseline.value = stableSerialize(current.value)
  }

  const isDirty = computed(() => stableSerialize(current.value) !== baseline.value)

  const canSubmit = computed(
    () => isDirty.value && (options.isSubmittable?.(current.value) ?? true),
  )

  return { capture, isDirty, canSubmit }
}
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && npm run test -- tests/useFormDirty.spec.ts
```
预期：全 PASS。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/composables/useFormDirty.ts frontend/tests/useFormDirty.spec.ts
git commit -m "feat(frontend): 表单脏检查 composable"
```

---

### Task 9: API 客户端支持 FormData、分页与响应头

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/records.ts`、`gifts.ts`、`funds.ts`

**Interfaces:**
- Produces:
  - `api.postForm<T>(path, form: FormData): Promise<T>`
  - `api.listPaged<T>(path): Promise<{ items: T[]; total: number }>`（`total` 取自 `X-Total-Count`）
  - `api.uploadTemp(file: File): Promise<{ temp_path: string }>`
  - types：`ActivityImageOut`、`ImageRefIn`、`Paged<T>`；`ActivityOut/Create/Update` 加 `images`

**为什么 `listPaged` 用回调拿响应头：** `request()` 只返回 body。加第三个参数 `onResponse` 让调用方读头，避免为分页复制一份错误处理与 401 逻辑。

- [ ] **Step 1: 改 client.ts**

`frontend/src/api/client.ts`：`request` 加第三个参数，并让 FormData 不被强制设成 JSON。

```ts
async function request<T>(
  path: string,
  options: RequestInit = {},
  onResponse?: (response: Response) => void,
): Promise<T> {
  const auth = useAuthStore()
  const headers = new Headers(options.headers)
  // FormData 必须让浏览器自己带 boundary；手动设 application/json 会让后端解析失败
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  if (auth.token) {
    headers.set('Authorization', `Bearer ${auth.token}`)
  }

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  onResponse?.(response)

  if (response.status === 401) {
    auth.logout()
    throw new ApiError('请先登录', 401)
  }
  if (response.status === 204) {
    return undefined as T
  }

  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError((body as { message?: string }).message ?? '请求失败', response.status)
  }
  return body as T
}
```

`api` 对象追加：

```ts
export const api = {
  // ...get/post/put/patch/delete 保持不变
  postForm: <T>(path: string, form: FormData) =>
    request<T>(path, { method: 'POST', body: form }),

  /** 分页列表：body 是数组，总数在 X-Total-Count 头里。 */
  listPaged: async <T>(path: string): Promise<Paged<T>> => {
    let total = 0
    const items = await request<T[]>(path, {}, (response) => {
      total = Number(response.headers.get('X-Total-Count') ?? 0)
    })
    return { items, total }
  },

  /** 上传单张图片到临时区，返回供表单引用的临时路径。 */
  uploadTemp: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ temp_path: string }>('/uploads/temp', { method: 'POST', body: form })
  },
}
```

导入 `Paged` 类型。

- [ ] **Step 2: 改 types.ts**

`frontend/src/api/types.ts`：活动区块加图片类型与字段。

```ts
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

/** 分页列表响应（items 为 body，total 来自 X-Total-Count 头） */
export interface Paged<T> {
  items: T[]
  total: number
}
```

`ActivityCreate` / `ActivityUpdate` 加 `images?: ImageRefIn[]`；`ActivityOut` 加 `images: ActivityImageOut[]`。

- [ ] **Step 3: 改三个 api 模块**

`records.ts` 的 `activitiesApi.list` 改为分页：

```ts
list: (params?: { search?: string; contactId?: number; limit?: number; offset?: number }) =>
  api.listPaged<ActivityOut>(
    withQuery('/records/activities', {
      search: params?.search,
      contact_id: params?.contactId,
      limit: params?.limit,
      offset: params?.offset,
    }),
  ),
```

`gifts.ts` / `funds.ts` 的 `list` 同样加 `limit` / `offset` 并改用 `api.listPaged`。
`records.ts` 另加图片读取地址助手：

```ts
/** 活动图片的鉴权读取地址（需登录态，经 useAuthedImage 取 blob）。 */
export function activityImageUrl(imageId: number, size: 'thumb' | 'full' = 'full'): string {
  return `/records/activities/images/${imageId}?size=${size}`
}
```

- [ ] **Step 4: 类型检查**

```bash
cd frontend && npx vue-tsc -b --noEmit
```
预期：会有**预期内的报错**——三个列表页仍按旧方式使用 `list()`（拿到的是 `{items,total}`）。这些在 Task 14、15 修。此处先确认没有其他类型错误。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/api
git commit -m "feat(api): 客户端支持 FormData、分页与 X-Total-Count"
```

---

### Task 10: useAuthedImage（鉴权图片加载）

**Files:**
- Create: `frontend/src/composables/useAuthedImage.ts`

**Interfaces:**
- Produces: `useAuthedImage(source: () => string | null | undefined) => { blobUrl: Ref<string | null> }`
  - `source` 返回的是**不含 `/api/v1` 前缀**的相对地址（如 `activityImageUrl(...)` 的产物）
  - 组件里直接 `<img :src="blobUrl ?? undefined">`

**为什么不能直接 `<img src>`：** 图片端点需要 Bearer 令牌，而 `<img>` 标签不会带自定义头。所以统一取 blob 再转 objectURL。

- [ ] **Step 1: 实现**

`frontend/src/composables/useAuthedImage.ts`：

```ts
/**
 * 鉴权图片加载：图片端点要求登录态，而 <img src> 无法携带 Authorization 头，
 * 因此统一用 fetch 取 blob 转 objectURL。
 *
 * 生命周期由调用方组件作用域决定：source 变化时自动换取新图并释放旧 objectURL，
 * 组件卸载时一并释放，避免长期浏览时的内存堆积。
 */
import { onScopeDispose, ref, watch, type Ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

const API_BASE = '/api/v1'

export function useAuthedImage(source: () => string | null | undefined): {
  blobUrl: Ref<string | null>
  loading: Ref<boolean>
  failed: Ref<boolean>
} {
  const blobUrl = ref<string | null>(null)
  const loading = ref(false)
  const failed = ref(false)
  let currentObjectUrl: string | null = null

  /** 释放当前 objectURL（换图与卸载都要走这里，防止内存泄漏）。 */
  function release(): void {
    if (currentObjectUrl) {
      URL.revokeObjectURL(currentObjectUrl)
      currentObjectUrl = null
    }
  }

  watch(
    source,
    async (path) => {
      release()
      blobUrl.value = null
      failed.value = false
      if (!path) return

      loading.value = true
      const auth = useAuthStore()
      try {
        const response = await fetch(`${API_BASE}${path}`, {
          headers: auth.token ? { Authorization: `Bearer ${auth.token}` } : {},
        })
        if (!response.ok) {
          failed.value = true
          return
        }
        const blob = await response.blob()
        // 快速切换图片时旧请求可能后到：只在仍是当前 path 时采用结果
        if (source() !== path) return
        currentObjectUrl = URL.createObjectURL(blob)
        blobUrl.value = currentObjectUrl
      } catch {
        failed.value = true
      } finally {
        loading.value = false
      }
    },
    { immediate: true },
  )

  onScopeDispose(release)

  return { blobUrl, loading, failed }
}
```

- [ ] **Step 2: 验证**

```bash
cd frontend && npx vue-tsc -b --noEmit
```
预期：无新增类型错误。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/composables/useAuthedImage.ts
git commit -m "feat(frontend): 鉴权图片加载 composable"
```

---

### Task 11: ImageUploader 组件

**Files:**
- Create: `frontend/src/components/ImageUploader.vue`

**Interfaces:**
- Props: `modelValue: ImageRefIn[]`
- Emits: `update:modelValue`
- 行为：多选上传（逐张串行）、缩略图网格、删除、上移/下移排序、首张标「封面」

**排序为什么用按钮而不是拖拽：** 拖拽要引入第三方库或手写一大段 HTML5 DnD，而上移/下移按钮用一个数组 splice 就能表达同一语义，且键盘可达（可访问性更好）。

- [ ] **Step 1: 实现**

`frontend/src/components/ImageUploader.vue`：

```vue
<script setup lang="ts">
/**
 * 活动图片上传器：选图后逐张传到临时区，提交时由表单把临时路径一起提交；
 * 已有图片只带 id，保持「提交数组顺序即展示顺序」的全量替换语义。
 */
import { computed, ref, watchEffect } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api/client'
import { ApiError } from '@/api/client'
import { activityImageUrl } from '@/api/records'
import { useAuthedImage } from '@/composables/useAuthedImage'
import type { ImageRefIn } from '@/api/types'

const props = defineProps<{ modelValue: ImageRefIn[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: ImageRefIn[]] }>()

const ACCEPT = '.jpg,.jpeg,.png,.webp'
const MAX_IMAGES = 20
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const images = computed(() => props.modelValue)

/** 预览地址：已有图走鉴权端点，新上传的走临时区端点。 */
function previewPath(item: ImageRefIn): string | null {
  if (item.id !== undefined) return activityImageUrl(item.id, 'thumb')
  if (item.temp_path) return `/uploads/${item.temp_path}`
  return null
}

/** 打开系统文件选择框。 */
function pickFiles(): void {
  fileInput.value?.click()
}

/** 逐张上传选中文件（串行，避免家庭网络下并发上传互相挤占）。 */
async function onFilesSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = '' // 允许重复选同一个文件
  if (!files.length) return

  const room = MAX_IMAGES - images.value.length
  if (room <= 0) {
    ElMessage.warning(`最多 ${MAX_IMAGES} 张图片`)
    return
  }

  uploading.value = true
  const added: ImageRefIn[] = []
  try {
    for (const file of files.slice(0, room)) {
      const { temp_path: tempPath } = await api.uploadTemp(file)
      added.push({ temp_path: tempPath })
    }
    emit('update:modelValue', [...images.value, ...added])
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '图片上传失败')
  } finally {
    uploading.value = false
  }
}

/** 移除一张图（已有图不放进提交数组即等于删除，符合全量替换语义）。 */
function removeAt(index: number): void {
  const next = [...images.value]
  next.splice(index, 1)
  emit('update:modelValue', next)
}

/** 与相邻项交换位置，用于调整封面。 */
function move(index: number, delta: number): void {
  const target = index + delta
  if (target < 0 || target >= images.value.length) return
  const next = [...images.value]
  ;[next[index], next[target]] = [next[target], next[index]]
  emit('update:modelValue', next)
}
</script>

<template>
  <div class="uploader">
    <div class="grid">
      <div v-for="(item, index) in images" :key="item.id ?? item.temp_path" class="cell">
        <AuthedThumb :path="previewPath(item)" />
        <span v-if="index === 0" class="cover">封面</span>
        <div class="actions">
          <el-button text size="small" :disabled="index === 0" @click="move(index, -1)">
            前移
          </el-button>
          <el-button
            text
            size="small"
            :disabled="index === images.length - 1"
            @click="move(index, 1)"
          >
            后移
          </el-button>
          <el-button text size="small" type="danger" @click="removeAt(index)">删除</el-button>
        </div>
      </div>

      <button v-if="images.length < MAX_IMAGES" class="add" type="button" @click="pickFiles">
        <span>{{ uploading ? '上传中…' : '+ 添加图片' }}</span>
      </button>
    </div>

    <p class="hint">第一张作为封面显示在联系人往来里；支持 jpg / png / webp，单张不超过 10MB</p>
    <input
      ref="fileInput"
      type="file"
      :accept="ACCEPT"
      multiple
      hidden
      @change="onFilesSelected"
    />
  </div>
</template>

<style scoped>
/* 样式只消费 design tokens，禁止硬编码色值 */
.grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.cell {
  position: relative;
  width: 96px;
}
.cover {
  position: absolute;
  top: 4px;
  left: 4px;
  padding: 1px 6px;
  border-radius: var(--crm-radius-control);
  background: var(--crm-seal);
  color: #fff;
  font-size: 12px;
}
.actions {
  display: flex;
  justify-content: center;
  gap: 2px;
}
.add {
  width: 96px;
  height: 96px;
  border: 1px dashed var(--crm-line);
  border-radius: var(--crm-radius-control);
  background: var(--crm-bone);
  color: var(--crm-muted);
  cursor: pointer;
  font-size: 13px;
}
.hint {
  margin: 8px 0 0;
  color: var(--crm-muted);
  font-size: 12px;
}
</style>
```

同一文件里内联一个只负责取图的子组件（避免为一张缩略图再开一个文件）：

```vue
<script lang="ts">
/** 缩略图：把鉴权取到的 blob 渲染出来，失败时留一个占位。 */
import { defineComponent } from 'vue'
import { useAuthedImage } from '@/composables/useAuthedImage'

export default defineComponent({})
</script>
```

**上面这个内联写法不要用**——Vue SFC 里一个文件只能有一个 `<script setup>`。改为在 `frontend/src/components/AuthedThumb.vue` 单独建一个小组件：

```vue
<script setup lang="ts">
/** 鉴权缩略图：拿 blob URL 渲染，取不到时显示占位块。 */
import { toRef } from 'vue'
import { useAuthedImage } from '@/composables/useAuthedImage'

const props = defineProps<{ path: string | null }>()
const { blobUrl, failed } = useAuthedImage(() => props.path)
</script>

<template>
  <img v-if="blobUrl" :src="blobUrl" class="thumb" alt="" />
  <div v-else class="placeholder" :class="{ failed }" />
</template>

<style scoped>
.thumb,
.placeholder {
  width: 96px;
  height: 96px;
  object-fit: cover;
  border-radius: var(--crm-radius-control);
  border: 1px solid var(--crm-line);
}
.placeholder {
  background: var(--crm-bone);
}
</style>
```

并把 `ImageUploader.vue` 里的 `<AuthedThumb :path="previewPath(item)" />` 配上导入：

```ts
import AuthedThumb from '@/components/AuthedThumb.vue'
```

- [ ] **Step 2: 验证（在开发环境手工核验）**

```bash
cd frontend && npx vue-tsc -b --noEmit
```
然后浏览器打开 `http://localhost:5180/activities`（Task 14 之后可完整验证上传；本步骤只确认类型与编译无误）。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/ImageUploader.vue frontend/src/components/AuthedThumb.vue
git commit -m "feat(frontend): 图片上传组件与鉴权缩略图"
```

---

### Task 12: ActivityFormDialog（活动共享表单弹窗）

**Files:**
- Create: `frontend/src/components/ActivityFormDialog.vue`

**Interfaces:**
- Props: `visible: boolean`、`activity: ActivityOut | null`（null 为新建）、`presetContactId?: number`
- Emits: `update:visible`、`saved`
- Consumes: `activitiesApi.create/update`、`useFormDirty`、`ImageUploader`、`useContactOptions`

- [ ] **Step 1: 实现**

```vue
<script setup lang="ts">
/**
 * 活动表单弹窗（D16：全站数据录入统一 el-dialog 居中弹窗，不用抽屉）。
 * 列表页「编辑」与详情页「查看详情」复用同一个组件，保证两处行为完全一致。
 * 保存按钮走 useFormDirty：无改动或必填未过一律置灰；取消/关闭不落库。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { activitiesApi } from '@/api/records'
import { ApiError } from '@/api/client'
import { useContactOptions } from '@/composables/useContactOptions'
import { useFormDirty } from '@/composables/useFormDirty'
import ImageUploader from '@/components/ImageUploader.vue'
import type { ActivityOut, ImageRefIn } from '@/api/types'

const props = defineProps<{
  visible: boolean
  activity: ActivityOut | null
  presetContactId?: number
}>()
const emit = defineEmits<{ 'update:visible': [value: boolean]; saved: [] }>()

const { options, load: loadContacts } = useContactOptions()
const saving = ref(false)

interface ActivityDraft {
  title: string
  occurred_at: number | null
  location: string
  detail: string
  participant_ids: number[]
  images: ImageRefIn[]
}

/** 空表单：occurred_at 默认当前时刻，省得每次手填。 */
function emptyDraft(): ActivityDraft {
  return {
    title: '',
    occurred_at: Date.now(),
    location: '',
    detail: '',
    participant_ids: props.presetContactId ? [props.presetContactId] : [],
    images: [],
  }
}

const form = ref<ActivityDraft>(emptyDraft())
const { capture, canSubmit } = useFormDirty(form, {
  isSubmittable: (draft) => draft.title.trim().length > 0,
})

const dialogTitle = computed(() => (props.activity ? '编辑活动' : '记一次活动'))

/** 打开时按编辑/新建分别回填并记录基线。 */
watch(
  () => props.visible,
  async (opened) => {
    if (!opened) return
    await loadContacts()
    const source = props.activity
    form.value = source
      ? {
          title: source.title,
          occurred_at: source.occurred_at ? new Date(source.occurred_at).getTime() : null,
          location: source.location ?? '',
          detail: source.detail ?? '',
          participant_ids: [...source.participant_ids],
          images: source.images.map((image) => ({ id: image.id })),
        }
      : emptyDraft()
    capture()
  },
  { immediate: true },
)

/** 提交：时间戳转 ISO，图片按数组顺序全量提交（后端据此重排与删除）。 */
async function submit(): Promise<void> {
  saving.value = true
  try {
    const payload = {
      title: form.value.title,
      occurred_at: form.value.occurred_at ? new Date(form.value.occurred_at).toISOString() : null,
      location: form.value.location || null,
      detail: form.value.detail || null,
      participant_ids: form.value.participant_ids,
      images: form.value.images,
    }
    if (props.activity) {
      await activitiesApi.update(props.activity.id, payload)
      ElMessage.success('活动已更新')
    } else {
      await activitiesApi.create(payload)
      ElMessage.success('活动已记录')
    }
    emit('saved')
    emit('update:visible', false)
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

/** 取消：不提交任何请求（脏检查让「误点」也不会写入）。 */
function close(): void {
  emit('update:visible', false)
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="dialogTitle"
    width="480px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <el-form label-position="top">
      <el-form-item label="标题" required>
        <el-input v-model="form.title" placeholder="如：家庭团圆饭" />
      </el-form-item>
      <el-form-item label="时间">
        <el-date-picker
          v-model="form.occurred_at"
          type="datetime"
          value-format="x"
          clearable
          class="full"
        />
      </el-form-item>
      <el-form-item label="地点">
        <el-input v-model="form.location" placeholder="选填" />
      </el-form-item>
      <el-form-item label="参与的人">
        <el-select v-model="form.participant_ids" multiple filterable placeholder="从名册选择（可多选）">
          <el-option v-for="opt in options" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="图片">
        <ImageUploader v-model="form.images" />
      </el-form-item>
      <el-form-item label="详情">
        <el-input v-model="form.detail" type="textarea" :rows="3" placeholder="发生了什么、聊了什么（选填）" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button text @click="close">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="!canSubmit" @click="submit">
        保存
      </el-button>
    </template>
  </el-dialog>
</template>
```

- [ ] **Step 2: 验证**

```bash
cd frontend && npx vue-tsc -b --noEmit
```
预期：本组件无类型错误（列表页的报错属 Task 14）。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/ActivityFormDialog.vue
git commit -m "feat(frontend): 活动共享表单弹窗"
```

---

### Task 13: GiftFormDialog 与 FundFormDialog

**Files:**
- Create: `frontend/src/components/GiftFormDialog.vue`
- Create: `frontend/src/components/FundFormDialog.vue`

**Interfaces:**
- 两者的 props / emits 与 `ActivityFormDialog` 一致（`visible` / `gift|flow` / `presetContactId?`）
- 不含 `ImageUploader`（图片是活动专属）

- [ ] **Step 1: 实现 GiftFormDialog**

```vue
<script setup lang="ts">
/**
 * 礼物表单弹窗（D16 居中弹窗）：列表页与联系人往来 Tab 共用同一组件。
 * 保存按钮走 useFormDirty 置灰策略；取消/关闭不落库。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { giftsApi } from '@/api/gifts'
import { ApiError } from '@/api/client'
import { useContactOptions } from '@/composables/useContactOptions'
import { useFormDirty } from '@/composables/useFormDirty'
import type { GiftOut } from '@/api/types'

const props = defineProps<{
  visible: boolean
  gift: GiftOut | null
  presetContactId?: number
}>()
const emit = defineEmits<{ 'update:visible': [value: boolean]; saved: [] }>()

const { options, load: loadContacts } = useContactOptions()
const saving = ref(false)

interface GiftDraft {
  direction: 'given' | 'received'
  title: string
  contact_id: number | null
  occasion: string
  amount: string
  given_at: string | null
  link: string
  description: string
}

/** 空表单：方向默认「我送出」。 */
function emptyDraft(): GiftDraft {
  return {
    direction: 'given',
    title: '',
    contact_id: props.presetContactId ?? null,
    occasion: '',
    amount: '',
    given_at: null,
    link: '',
    description: '',
  }
}

const form = ref<GiftDraft>(emptyDraft())
const { capture, canSubmit } = useFormDirty(form, {
  isSubmittable: (draft) => draft.title.trim().length > 0,
})

const dialogTitle = computed(() => (props.gift ? '编辑礼物' : '记一笔礼物'))

watch(
  () => props.visible,
  async (opened) => {
    if (!opened) return
    await loadContacts()
    const source = props.gift
    form.value = source
      ? {
          direction: source.direction,
          title: source.title,
          contact_id: source.contact_id,
          occasion: source.occasion ?? '',
          amount: source.amount ?? '',
          given_at: source.given_at,
          link: source.link ?? '',
          description: source.description ?? '',
        }
      : emptyDraft()
    capture()
  },
  { immediate: true },
)

/** 提交：按新建/编辑分流，成功与失败都由 ElMessage 气泡反馈。 */
async function submit(): Promise<void> {
  saving.value = true
  try {
    const payload = {
      direction: form.value.direction,
      title: form.value.title,
      contact_id: form.value.contact_id,
      occasion: form.value.occasion || null,
      amount: form.value.amount || null,
      given_at: form.value.given_at,
      link: form.value.link || null,
      description: form.value.description || null,
    }
    if (props.gift) {
      await giftsApi.update(props.gift.id, payload)
      ElMessage.success('礼物已更新')
    } else {
      await giftsApi.create(payload)
      ElMessage.success('礼物已记下')
    }
    emit('saved')
    emit('update:visible', false)
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="dialogTitle"
    width="480px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <el-form label-position="top">
      <el-form-item label="方向">
        <el-radio-group v-model="form.direction">
          <el-radio-button value="given">我送出</el-radio-button>
          <el-radio-button value="received">我收到</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="礼物名称" required>
        <el-input v-model="form.title" placeholder="如：龙井茶" />
      </el-form-item>
      <el-form-item label="对象">
        <el-select v-model="form.contact_id" filterable clearable placeholder="给谁/谁送的">
          <el-option v-for="opt in options" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="场合">
        <el-input v-model="form.occasion" placeholder="生日、婚礼、探病…（选填）" />
      </el-form-item>
      <el-form-item label="金额（元）">
        <el-input v-model="form.amount" placeholder="选填，如 388.00" />
      </el-form-item>
      <el-form-item label="日期">
        <el-date-picker v-model="form.given_at" type="date" value-format="YYYY-MM-DD" clearable class="full" />
      </el-form-item>
      <el-form-item label="购买/参考链接">
        <el-input v-model="form.link" placeholder="选填" />
      </el-form-item>
      <el-form-item label="礼物说明">
        <el-input v-model="form.description" type="textarea" :rows="3" placeholder="支持 Markdown（选填）" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button text @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="!canSubmit" @click="submit">
        保存
      </el-button>
    </template>
  </el-dialog>
</template>
```

- [ ] **Step 2: 实现 FundFormDialog**

结构同上，把礼物字段换成资金字段（`direction` out/in、`category` loan/repayment/gift_money/other、`amount` 必填、`occurred_at` 必填、`due_at`、`description`），校验改为：

```ts
const { capture, canSubmit } = useFormDirty(form, {
  isSubmittable: (draft) => draft.amount.trim().length > 0 && !!draft.occurred_at,
})
```

`emptyDraft()` 的 `occurred_at` 默认今天（`new Date().toISOString().slice(0, 10)`），标题用 `dialogTitle = computed(() => (props.flow ? '编辑记录' : '记一笔资金往来'))`，提交调 `fundsApi.create/update`，成功气泡分别是「资金记录已记下」「资金记录已更新」。

- [ ] **Step 3: 验证并提交**

```bash
cd frontend && npx vue-tsc -b --noEmit
git add frontend/src/components/GiftFormDialog.vue frontend/src/components/FundFormDialog.vue
git commit -m "feat(frontend): 礼物与资金共享表单弹窗"
```

---

## Phase 6：列表页接入共享弹窗与分页

### Task 14: ActivitiesPage 接入

**Files:**
- Modify: `frontend/src/pages/ActivitiesPage.vue`

**Interfaces:**
- Consumes: `ActivityFormDialog`（Task 12）、`activitiesApi.list`（Task 9 起返回 `{items,total}`）

- [ ] **Step 1: 换掉内联弹窗与加载逻辑**

脚本部分：删掉本地 `form` / `emptyForm` / `openCreate` / `openEdit` / `submit` 与内联 `el-dialog`，改为共享组件 + 分页状态。

```ts
const PAGE_SIZE = 20
const page = ref(1)
const total = ref(0)
const dialogVisible = ref(false)
const editingActivity = ref<ActivityOut | null>(null)

/** 拉取当前页（关键字搜索由后端执行，总数用于页码）。 */
async function loadActivities(): Promise<void> {
  loading.value = true
  try {
    const { items, total: count } = await activitiesApi.list({
      search: search.value || undefined,
      limit: PAGE_SIZE,
      offset: (page.value - 1) * PAGE_SIZE,
    })
    activities.value = items
    total.value = count
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('活动加载失败')
  } finally {
    loading.value = false
  }
}

/** 打开新建弹窗。 */
function openCreate(): void {
  editingActivity.value = null
  dialogVisible.value = true
}

/** 打开编辑弹窗。 */
function openEdit(activity: ActivityOut): void {
  editingActivity.value = activity
  dialogVisible.value = true
}

/** 搜索词变化必须回到第 1 页，否则会停在越界页看到空表（Review Focus #4）。 */
watch(search, () => {
  page.value = 1
  void loadActivities()
})
```

模板部分：表头按钮 `@click="openCreate"`，行内「编辑」改为 `@click="openEdit(row)"`，表格下方加：

```vue
<el-pagination
  v-model:current-page="page"
  :page-size="PAGE_SIZE"
  :total="total"
  layout="prev, pager, next, total"
  class="pager"
  @current-change="loadActivities"
/>

<ActivityFormDialog
  v-model:visible="dialogVisible"
  :activity="editingActivity"
  @saved="loadActivities"
/>
```

样式加：

```css
.pager {
  margin-top: 14px;
  justify-content: flex-end;
}
```

- [ ] **Step 2: 验证**

```bash
cd frontend && npx vue-tsc -b --noEmit && npm run build
```
浏览器核验（开发环境已跑）：`/activities` 页显示 20 条一页、页码可翻、搜索一个字后自动回第 1 页、点「编辑」打开的是居中弹窗且**保存按钮初始置灰**、改一个字符后变可点、点取消后再打开数据未变。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/pages/ActivitiesPage.vue
git commit -m "feat(activities): 接入共享弹窗与页码分页"
```

---

### Task 15: GiftsPage 与 FundsPage 接入

**Files:**
- Modify: `frontend/src/pages/GiftsPage.vue`
- Modify: `frontend/src/pages/FundsPage.vue`

**Interfaces:**
- Consumes: `GiftFormDialog` / `FundFormDialog`（Task 13）

- [ ] **Step 1: 两个页面按同一模式改造**

与 Task 14 完全同构：删本地表单状态与内联弹窗 → 接共享组件；加 `page` / `total` / `PAGE_SIZE = 20`；`load*()` 改用 `{items,total}`；**每个筛选条件（搜索、方向、类别、状态）都要 `watch` 回到第 1 页**。

FundsPage 的 `watch` 示例：

```ts
/** 任一筛选条件变化都回到第 1 页，避免停在越界页看到空表。 */
watch([search, direction, category, status], () => {
  page.value = 1
  void loadFunds()
})
```

- [ ] **Step 2: 逐页核验筛选回页**

浏览器核验：在 `/funds` 翻到第 2 页，把「方向」筛选切成另一档 → 应自动回到第 1 页并显示结果（不是空表）。`/gifts` 同样验一次。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/pages/GiftsPage.vue frontend/src/pages/FundsPage.vue
git commit -m "feat(gifts,funds): 接入共享弹窗与页码分页"
```

---

### Task 16: 其余三个弹窗加脏检查

**Files:**
- Modify: `frontend/src/pages/TasksPage.vue`
- Modify: `frontend/src/pages/WishlistPage.vue`
- Modify: `frontend/src/pages/ContactsPage.vue`

**范围说明：** 这三个页面的弹窗**不抽成组件**（它们不在联系人往来里，抽了属于非必要扩散），但保存按钮行为必须与抽出来的三个一致——否则又会出现"某几个页面行为不一样"。

- [ ] **Step 1: 每个页面接入 useFormDirty**

以 TasksPage 为例：

```ts
import { useFormDirty } from '@/composables/useFormDirty'

const { capture, canSubmit } = useFormDirty(form, {
  isSubmittable: (draft) => draft.title.trim().length > 0,
})
```

在 `openCreate()` / `openEdit()` 设置完 `form.value` 之后调用 `capture()`；把保存按钮的 `:disabled="!form.title.trim()"` 换成 `:disabled="!canSubmit"`。

`WishlistPage` 用 `draft.title.trim().length > 0`；`ContactsPage` 的 `isSubmittable` 用：

```ts
isSubmittable: (draft) => draft.last_name.trim().length > 0 || draft.first_name.trim().length > 0,
```

（名册允许只填名不填姓，与原表单校验一致。）

- [ ] **Step 2: 核验「取消不落库」（Review Focus #5）**

三个页面各做一次：打开弹窗 → 改一个字段 → 点「取消」→ 重新打开同一记录 → **字段应是原值**（脏检查只管按钮；这条验证的是"取消不发请求"这一既有行为没被破坏）。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/pages/TasksPage.vue frontend/src/pages/WishlistPage.vue frontend/src/pages/ContactsPage.vue
git commit -m "feat(frontend): 待办/心愿/名册弹窗统一脏检查"
```

---

## Phase 7：联系人往来改 Tabs

### Task 17: RecordTimeline 组件（单类型时间线 + 无限滚动）

**Files:**
- Create: `frontend/src/components/RecordTimeline.vue`
- Modify: `frontend/src/api/records.ts`（加归一助手，或放在组件内）

**Interfaces:**
- Props: `source: 'activity' | 'gift' | 'fund'`、`contactId: number`
- Emits: `open-detail: [payload: { source: string; record: TimelineRecord }]`
- Exposes: `reload(): Promise<void>`（父页面在保存/删除后刷新当前 tab）
- Produces: `TimelineRecord` 类型（三源归一后的展示形状）

- [ ] **Step 1: 实现**

```vue
<script setup lang="ts">
/**
 * 单类型往来时间线：按 source 拉对应模块的分页接口，滚动到底自动加载下一页。
 *
 * 拆成三个 Tab 各自分页后，不再需要 dashboard 的聚合接口——聚合服务仍保留给
 * AI 工具 get_contact_timeline 使用，前端不再依赖它。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { activitiesApi, activityImageUrl, tasksApi } from '@/api/records'
import { giftsApi } from '@/api/gifts'
import { fundsApi } from '@/api/funds'
import { ApiError } from '@/api/client'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import AuthedThumb from '@/components/AuthedThumb.vue'

const props = defineProps<{ source: 'activity' | 'gift' | 'fund'; contactId: number }>()
const emit = defineEmits<{
  'open-detail': [payload: { source: 'activity' | 'gift' | 'fund'; record: TimelineRecord }]
}>()

const PAGE_SIZE = 20
const auth = useAuthStore()

/** 三源归一后的展示形状：模板只认这一套字段，避免在模板里写三套分支。 */
export interface TimelineRecord {
  id: number
  occurredAt: string | null
  title: string
  summary: string | null
  amount: string | null
  direction: string | null
  extraLabel: string | null
  ownerUserId: number
  coverImageId: number | null
}

const records = ref<TimelineRecord[]>([])
const total = ref(0)
const loading = ref(false)
const sentinel = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

const hasMore = computed(() => records.value.length < total.value)

/** 活动 → 归一记录（封面取 sort_order 最小的一张）。 */
function fromActivity(raw: Record<string, unknown>): TimelineRecord {
  const images = (raw.images ?? []) as { id: number; sort_order: number }[]
  const cover = [...images].sort((a, b) => a.sort_order - b.sort_order)[0]
  return {
    id: raw.id as number,
    occurredAt: (raw.occurred_at as string | null) ?? null,
    title: raw.title as string,
    summary: (raw.location as string | null) ?? null,
    amount: null,
    direction: null,
    extraLabel: null,
    ownerUserId: raw.owner_user_id as number,
    coverImageId: cover?.id ?? null,
  }
}

/** 礼物 → 归一记录。 */
function fromGift(raw: Record<string, unknown>): TimelineRecord {
  return {
    id: raw.id as number,
    occurredAt: (raw.given_at as string | null) ?? null,
    title: raw.title as string,
    summary: (raw.description as string | null) ?? null,
    amount: (raw.amount as string | null) ?? null,
    direction: (raw.direction as string | null) ?? null,
    extraLabel: (raw.occasion as string | null) ?? null,
    ownerUserId: raw.owner_user_id as number,
    coverImageId: null,
  }
}

/** 资金 → 归一记录（标题按类别生成，与旧聚合口径一致）。 */
function fromFund(raw: Record<string, unknown>): TimelineRecord {
  return {
    id: raw.id as number,
    occurredAt: (raw.occurred_at as string | null) ?? null,
    title: FUND_LABELS[raw.category as string] ?? '资金事项',
    summary: (raw.description as string | null) ?? null,
    amount: (raw.amount as string | null) ?? null,
    direction: (raw.direction as string | null) ?? null,
    extraLabel: raw.status === 'settled' ? '已结清' : null,
    ownerUserId: raw.owner_user_id as number,
    coverImageId: null,
  }
}

const FUND_LABELS: Record<string, string> = {
  loan: '借款',
  repayment: '还款',
  gift_money: '礼金',
  other: '其他',
}

/** 按 source 分派到对应模块的分页接口。 */
async function fetchPage(offset: number): Promise<{ items: TimelineRecord[]; total: number }> {
  const params = { contactId: props.contactId, limit: PAGE_SIZE, offset }
  if (props.source === 'activity') {
    const page = await activitiesApi.list(params)
    return { items: page.items.map((item) => fromActivity(item as never)), total: page.total }
  }
  if (props.source === 'gift') {
    const page = await giftsApi.list(params)
    return { items: page.items.map((item) => fromGift(item as never)), total: page.total }
  }
  const page = await fundsApi.list(params)
  return { items: page.items.map((item) => fromFund(item as never)), total: page.total }
}

/** 加载下一页并追加（首屏与滚动加载共用）。 */
async function loadMore(): Promise<void> {
  if (loading.value || !hasMore.value) return
  loading.value = true
  try {
    const page = await fetchPage(records.value.length)
    records.value = [...records.value, ...page.items]
    total.value = page.total
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('往来记录加载失败')
  } finally {
    loading.value = false
  }
}

/** 重置并重新加载首屏（保存/删除后由父页面调用）。 */
async function reload(): Promise<void> {
  records.value = []
  total.value = 0
  await loadMore()
}

/** 删除该条记录（仅记录人本人可见按钮，后端仍会独立校验）。 */
async function remove(record: TimelineRecord): Promise<void> {
  try {
    if (props.source === 'activity') await activitiesApi.remove(record.id)
    else if (props.source === 'gift') await giftsApi.remove(record.id)
    else await fundsApi.remove(record.id)
    ElMessage.success('已删除')
    await reload()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '删除失败')
  }
}

/** 时间戳展示：日期 + 时分（无日期显示占位）。 */
function formatTime(value: string | null): string {
  if (!value) return '未定时间'
  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** 金额展示（带正负号，流出为负）。 */
function amountText(record: TimelineRecord): string | null {
  if (!record.amount) return null
  const negative = record.direction === 'out' || record.direction === 'given'
  return `${negative ? '−' : '+'}¥${record.amount}`
}

onMounted(() => {
  observer = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) void loadMore()
  })
  if (sentinel.value) observer.observe(sentinel.value)
  void loadMore()
})

onBeforeUnmount(() => observer?.disconnect())

watch(() => props.contactId, reload)
watch(() => props.source, reload)

defineExpose({ reload })
</script>

<template>
  <el-timeline>
    <el-timeline-item
      v-for="record in records"
      :key="`${source}-${record.id}`"
      :timestamp="formatTime(record.occurredAt)"
      placement="top"
    >
      <el-card shadow="always" class="tl-card crm-rise" :body-style="{ padding: '12px 16px' }">
        <div class="tl-head">
          <AuthedThumb
            v-if="record.coverImageId"
            :path="activityImageUrl(record.coverImageId, 'thumb')"
            class="tl-cover"
          />
          <div class="tl-main">
            <span class="tl-title">{{ record.title }}</span>
            <span v-if="amountText(record)" class="tl-amount">{{ amountText(record) }}</span>
          </div>
        </div>
        <div class="tl-meta">
          <span v-if="record.extraLabel">{{ record.extraLabel }}</span>
          <span v-if="record.summary">{{ record.summary }}</span>
        </div>
        <div class="tl-actions">
          <el-button text size="small" @click="emit('open-detail', { source, record })">
            查看详情
          </el-button>
          <el-popconfirm
            v-if="record.ownerUserId === auth.user?.id"
            title="删除这条记录？"
            confirm-button-text="删除"
            cancel-button-text="取消"
            @confirm="remove(record)"
          >
            <template #reference>
              <el-button text size="small" type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </div>
      </el-card>
    </el-timeline-item>
  </el-timeline>
  <div ref="sentinel" class="sentinel">
    <span v-if="loading" class="hint">加载中…</span>
    <span v-else-if="hasMore" class="hint">继续下滑，加载更早的记录…</span>
  </div>
</template>

<style scoped>
.tl-card {
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
}
.tl-head {
  display: flex;
  gap: 12px;
  align-items: center;
}
.tl-cover {
  flex-shrink: 0;
}
.tl-cover :deep(img) {
  width: 56px;
  height: 56px;
}
.tl-main {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.tl-title {
  font-size: 16px;
  color: var(--crm-ink);
}
.tl-amount {
  color: var(--crm-muted);
  font-size: 14px;
}
.tl-meta {
  display: flex;
  gap: 10px;
  margin-top: 6px;
  color: var(--crm-muted);
  font-size: 13px;
}
.tl-actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 6px;
}
.sentinel {
  padding: 8px 0 4px;
  text-align: center;
}
.hint {
  color: var(--crm-muted);
  font-size: 13px;
}
</style>
```

**注意：** `TimelineRecord` 用 `export interface` 在 `<script setup>` 里导出在 Vue 3.5 下不可靠——把它移到 `frontend/src/api/types.ts`（或新建 `frontend/src/types/timeline.ts`）后 import，父页面也从同一处导入。

- [ ] **Step 2: 验证**

```bash
cd frontend && npx vue-tsc -b --noEmit
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/RecordTimeline.vue frontend/src/api/types.ts
git commit -m "feat(frontend): 单类型往来时间线组件"
```

---

### Task 18: 活动图片大图查看器

**Files:**
- Create: `frontend/src/components/ActivityGalleryDialog.vue`
- Modify: `frontend/src/components/AuthedThumb.vue`（加 `variant` 支持大图尺寸）
- Modify: `frontend/src/components/RecordTimeline.vue`（封面可点开）

**Interfaces:**
- `AuthedThumb` 新增可选 prop `variant?: 'thumb' | 'full'`（默认 `thumb`）
- `ActivityGalleryDialog`：props `visible: boolean`、`activityId: number | null`；emits `update:visible`
- Consumes: `activitiesApi.get`（拿该活动的全部图片）、`activityImageUrl`

**为什么单独做一个查看器：** spec 4.2 要求「时间线卡片点击缩略图开大图查看器，可左右翻看该活动其余图片」。归一记录只带封面 id，所以点开时按 id 拉一次活动详情取全部图片。这里用自研的左右切换而不是 `el-image` 的 `preview-src-list`——后者要求预览列表在打开前就已是可用 URL，而我们的图片要先经过鉴权 fetch 才有 blob URL，时序对不上。

- [ ] **Step 1: 给 AuthedThumb 加尺寸变体**

`frontend/src/components/AuthedThumb.vue` 的 script 与模板改为：

```vue
<script setup lang="ts">
/** 鉴权缩略图：拿 blob URL 渲染，取不到时显示占位块。 */
import { useAuthedImage } from '@/composables/useAuthedImage'

const props = defineProps<{ path: string | null; variant?: 'thumb' | 'full' }>()
const { blobUrl, failed } = useAuthedImage(() => props.path)
</script>

<template>
  <img v-if="blobUrl" :src="blobUrl" class="image" :class="variant ?? 'thumb'" alt="" />
  <div v-else class="placeholder" :class="[variant ?? 'thumb', { failed }]" />
</template>

<style scoped>
.image,
.placeholder {
  object-fit: cover;
  border-radius: var(--crm-radius-control);
  border: 1px solid var(--crm-line);
}
.thumb {
  width: 96px;
  height: 96px;
}
.full {
  width: 100%;
  max-height: 60vh;
  object-fit: contain;
  border: none;
}
.placeholder {
  background: var(--crm-bone);
}
</style>
```

（原有 `thumb` 尺寸保持不变，避免影响 Task 11 的上传器网格。）

- [ ] **Step 2: 实现查看器**

`frontend/src/components/ActivityGalleryDialog.vue`：

```vue
<script setup lang="ts">
/**
 * 活动图片查看器：拉该活动的全部图片（按展示顺序），支持左右翻看。
 * 图片走鉴权端点，所以用 AuthedThumb 的 full 变体而不是原生 img。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { activitiesApi, activityImageUrl } from '@/api/records'
import { ApiError } from '@/api/client'
import AuthedThumb from '@/components/AuthedThumb.vue'

const props = defineProps<{ visible: boolean; activityId: number | null }>()
const emit = defineEmits<{ 'update:visible': [value: boolean] }>()

const imageIds = ref<number[]>([])
const index = ref(0)

const currentPath = computed(() =>
  imageIds.value.length ? activityImageUrl(imageIds.value[index.value]) : null,
)
const total = computed(() => imageIds.value.length)

watch(
  () => props.visible,
  async (opened) => {
    if (!opened || props.activityId === null) return
    index.value = 0
    imageIds.value = []
    try {
      const activity = await activitiesApi.get(props.activityId)
      imageIds.value = [...activity.images]
        .sort((left, right) => left.sort_order - right.sort_order)
        .map((image) => image.id)
    } catch (error) {
      ElMessage.error(error instanceof ApiError ? error.message : '图片加载失败')
    }
  },
  { immediate: true },
)
</script>

<template>
  <el-dialog
    :model-value="visible"
    title="活动图片"
    width="720px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <div v-if="total" class="viewer">
      <AuthedThumb :path="currentPath" variant="full" />
      <div class="nav">
        <el-button :disabled="index === 0" @click="index -= 1">上一张</el-button>
        <span class="counter">{{ index + 1 }} / {{ total }}</span>
        <el-button :disabled="index === total - 1" @click="index += 1">下一张</el-button>
      </div>
    </div>
    <p v-else class="empty">这个活动还没有图片</p>
  </el-dialog>
</template>

<style scoped>
.viewer {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
}
.counter {
  color: var(--crm-muted);
  font-size: 13px;
}
.empty {
  margin: 0;
  color: var(--crm-muted);
  text-align: center;
}
</style>
```

- [ ] **Step 3: RecordTimeline 封面可点开**

`frontend/src/components/RecordTimeline.vue`：script 加

```ts
const galleryVisible = ref(false)
const galleryActivityId = ref<number | null>(null)

/** 打开该活动的图片查看器（只有活动源有图片）。 */
function openGallery(record: TimelineRecord): void {
  galleryActivityId.value = record.id
  galleryVisible.value = true
}
```

模板里封面改为可点：

```vue
  <button
    v-if="record.coverImageId"
    type="button"
    class="cover-button"
    @click="openGallery(record)"
  >
    <AuthedThumb :path="activityImageUrl(record.coverImageId, 'thumb')" />
  </button>
```

并在 `</template>` 前加：

```vue
  <ActivityGalleryDialog v-model:visible="galleryVisible" :activity-id="galleryActivityId" />
```

样式加：

```css
.cover-button {
  padding: 0;
  border: none;
  background: none;
  cursor: pointer;
}
```

- [ ] **Step 4: 核验并提交**

```bash
cd frontend && npx vue-tsc -b --noEmit
```
浏览器核验：往来「活动」tab 点封面 → 弹出查看器，左右切换能看到该活动的全部图片。Task 19 完成后可完整验证。

```bash
git add frontend/src/components/ActivityGalleryDialog.vue frontend/src/components/AuthedThumb.vue frontend/src/components/RecordTimeline.vue
git commit -m "feat(frontend): 活动图片大图查看器"
```

---

### Task 19: ContactDetailPage 往来区改 Tabs

**Files:**
- Modify: `frontend/src/pages/ContactDetailPage.vue`

**Interfaces:**
- Consumes: `RecordTimeline`（Task 17）、三个共享弹窗（Task 12/13）
- 移除：对 `dashboardApi.timeline` 的调用与相关分页哨兵逻辑

- [ ] **Step 1: 改脚本**

删掉 `timelineAll` / `timelineItems` / `timelineSentinel` / `hasMoreTimeline` / `loadTimeline` 及 `dashboardApi.timeline` 导入，替换为：

```ts
const activeTab = ref<'activity' | 'gift' | 'fund'>('activity')
const timelineRefs = ref<Record<string, { reload: () => Promise<void> } | null>>({})

// 三个弹窗的可见性与编辑对象
const activityDialogVisible = ref(false)
const editingActivity = ref<ActivityOut | null>(null)
const giftDialogVisible = ref(false)
const editingGift = ref<GiftOut | null>(null)
const fundDialogVisible = ref(false)
const editingFlow = ref<FundFlowOut | null>(null)

/** 打开某条记录的详情弹窗（与列表页同一个组件，行为一致）。 */
function openRecordDetail(payload: { source: string; record: TimelineRecord }): void {
  if (payload.source === 'activity') {
    // 时间线只带归一字段，详情需要完整记录：按 id 拉一次
    void openActivityById(payload.record.id)
  } else if (payload.source === 'gift') {
    void openGiftById(payload.record.id)
  } else {
    void openFundById(payload.record.id)
  }
}

/** 拉完整记录后打开编辑弹窗（归一记录字段不全，不能直接喂给表单）。 */
async function openActivityById(id: number): Promise<void> {
  try {
    editingActivity.value = await activitiesApi.get(id)
    activityDialogVisible.value = true
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '打开失败')
  }
}
```

（`openGiftById` / `openFundById` 同构，分别调 `giftsApi.get` / `fundsApi.get`。）

保存后刷新当前 tab：

```ts
/** 保存后刷新当前 Tab 的数据（各 tab 各自分页，互不影响）。 */
async function refreshActiveTab(): Promise<void> {
  await timelineRefs.value[activeTab.value]?.reload()
}
```

- [ ] **Step 2: 改模板**

「往 来」区块替换为：

```vue
<section class="block">
  <div class="block-head">
    <h2 class="block-title">往 来</h2>
  </div>
  <el-tabs v-model="activeTab">
    <el-tab-pane label="活动" name="activity">
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
    <el-tab-pane label="资金往来" name="fund">…同构…</el-tab-pane>
    <el-tab-pane label="礼物往来" name="gift">…同构…</el-tab-pane>
  </el-tabs>
</section>

<ActivityFormDialog
  v-model:visible="activityDialogVisible"
  :activity="editingActivity"
  :preset-contact-id="contactId"
  @saved="refreshActiveTab"
/>
<GiftFormDialog v-model:visible="giftDialogVisible" :gift="editingGift" :preset-contact-id="contactId" @saved="refreshActiveTab" />
<FundFormDialog v-model:visible="fundDialogVisible" :flow="editingFlow" :preset-contact-id="contactId" @saved="refreshActiveTab" />
```

`openNewActivity()` 把 `editingActivity` 置 null、打开弹窗（新建时自动带当前联系人为参与者，靠 `presetContactId`）。

- [ ] **Step 3: 核验**

浏览器逐项验证：
1. 三个 tab 各自加载、滚动到底能追加更多。
2. 每张卡片有「查看详情」「删除」；用家人账号看别人的记录时**没有删除按钮**。
3. 点「查看详情」弹出的是居中弹窗、字段已回填、**保存按钮置灰**。
4. 改一个字段 → 保存 → 气泡提示 + 当前 tab 刷新且能看到改动。
5. 点某个 tab 的「记一笔」→ 新建弹窗里参与者已预选当前联系人。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/pages/ContactDetailPage.vue
git commit -m "feat(contacts): 往来区改三 Tab 时间线"
```

---

## Phase 8：文档同步与收尾

### Task 20: 文档登记

**Files:**
- Modify: `TECH_DECISIONS.md`、`ARCHITECTURE.md`、`DATA_MODEL.md`、`DESIGN.md`

- [ ] **Step 1: TECH_DECISIONS.md**

- 决策总览表：D10 行改为 `| D10 | 附件/照片存储：**本地卷**（配置项 UPLOAD_DIR + compose named volume），DB 只存相对路径 | ✅ | 2026-09-25 |`
- 追加两个小节（**文件末尾**，与既有 D16/D17 同处）：
  - **D18 图片存储与两阶段上传**：本地卷 + 临时区/正式区两段式；先在临时区拿路径、表单 JSON 提交引用、保存时才 promote；图片读取走鉴权端点（不静态挂载）；缩略图长边 400px，新增依赖 Pillow 12.3.0。
  - **D19 联系人往来 Tabs 化**：往来区拆活动/资金/礼物三个 Tab，各自分页；前端不再调用 dashboard 聚合接口（该接口因 AI 工具 `get_contact_timeline` 继续保留）；列表接口统一 `limit` 默认 20、上限 200，总数走 `X-Total-Count`。

- [ ] **Step 2: ARCHITECTURE.md**

- 第 1 节模块表：新增一行 `| L0 横切 | storage | app/services/storage.py | — | 文件存储唯一实现点（临时区/正式区/缩略图/路径安全），配置注入、无表无状态 | ✅ |`；新增 `| L0 横切 | uploads | app/modules/uploads/ | — | 通用临时上传与本人读取端点；业务图片鉴权归各业务模块 | ✅ |`
- 第 3 节表归属：加 `| activity_images | records | activities（级联删） |`
- 第 4 节接口地图：`/api/v1/uploads` 前缀一行；records 行补 `GET /records/activities/images/{id}` 与 `contact_id`/`limit`/`offset`
- 第 6 节唯一口径表加一行：`| 文件存储（临时区/正式区/缩略图/路径安全） | app/services/storage.py |`
- 第 6 节备注补一句：dashboard 的 `GET /contacts/{id}/timeline` 聚合接口**保留供 AI 工具使用**，前端已改为按 Tab 分别调用三个列表接口。

- [ ] **Step 3: DATA_MODEL.md**

补 `activity_images` 字段级定义（列名、类型、约束、注释），与 `activity_participants` 并列。

- [ ] **Step 4: DESIGN.md**

组件规则后补一节「图片与时间线」：缩略图 96px 方形圆角（上传器）/ 56px（时间线卡片）、封面用印泥红小标、时间线卡片操作按钮右对齐、上传器空位用虚线骨灰白底。

- [ ] **Step 5: 提交**

```bash
git add TECH_DECISIONS.md ARCHITECTURE.md DATA_MODEL.md DESIGN.md
git commit -m "docs: 登记 D18/D19 与模块、表、口径变更"
```

---

### Task 21: 全量验证与清理

**Files:** 无新增

- [ ] **Step 1: 后端全绿**

```bash
cd backend && uv run pytest && uv run ruff check .
```

- [ ] **Step 2: 前端全绿**

```bash
cd frontend && npm run test && npm run build
```

- [ ] **Step 3: 端到端手工核验（开发环境）**

`./dev.sh` 起服务后逐项走一遍：

1. 活动加 3 张图 → 保存 → 联系人往来「活动」tab 卡片显示**第一张**为封面。
2. 点封面缩略图 → 弹出图片查看器，左右切换能看到该活动的**全部**图片（含第 2、3 张）。
3. 编辑活动：删掉中间一张、把第三张前移 → 保存 → 时间线封面随之变化。
4. 用家人账号（`tong`）登录看同一联系人：能看到 `family` 可见的活动与其图片，**没有删除按钮**，编辑其活动应报 403。
5. 删除活动 → 卡片消失；确认 `backend/uploads/activities/` 下对应文件也被删（`deferred delete` 生效）。
6. 三个列表页：翻页、搜索、筛选回第 1 页。
7. 停止一次服务再启动，确认 `cleanup_temp()` 不会误删正式区文件。

- [ ] **Step 4: 遗留项交代**

若核验中发现与本计划不符之处，向用户明确报告；无则说明全部通过。
