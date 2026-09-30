"""文件存储唯一实现点（L0 横切，D18）：临时区、正式区、缩略图、路径安全。

无表无状态、不判权——配置由 core.config 注入，HTTP 与鉴权在各业务模块。
文件删除必须发生在事务提交之后，故提供 defer_delete() 登记、由 after_commit 事件真正删盘。
"""

import io
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationError

# 只收这四种；HEIC 是手机直出格式但需额外解码库，明确不支持
ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
MAX_IMAGE_BYTES = 10 * 1024 * 1024
THUMB_MAX_EDGE = 400
TEMP_TTL_HOURS = 24

# 扩展名 → MIME：随临时文件按原格式喂给视觉模型，与 ALLOWED_EXTENSIONS 白名单一致
_IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def image_mime(extension: str) -> str:
    """按小写扩展名（含点）取 MIME；白名单外的兜底 jpeg——save_temp 已把过格式关。"""
    return _IMAGE_MIME.get(extension.lower(), "image/jpeg")


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


def _ensure_decodable(content: bytes) -> None:
    """校验字节流确实是一张可解码的图片。

    扩展名可以随便改（iPhone 直出的 HEIC 改名成 .jpg 很常见），所以内容必须验。
    在上传入口挡住，promotion 阶段就不可能因解码失败而中断——那会留下已搬进
    正式区却没有任何引用指向的孤儿文件（cleanup_temp 只扫临时区，回收不了）。
    """
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        # verify() 只查结构，截断文件可能蒙混过关；再真正解一遍像素
        with Image.open(io.BytesIO(content)) as image:
            image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("这不是有效的图片文件") from exc


def save_temp(user_id: int, filename: str, content: bytes) -> str:
    """把上传字节写入该用户的临时区，返回相对路径。

    文件名由服务端生成（不采用客户端文件名）；扩展名走白名单，内容还要能解码。
    """
    if len(content) > MAX_IMAGE_BYTES:
        raise ValidationError("单张图片不能超过 10MB")
    extension = validate_image_extension(filename)
    _ensure_decodable(content)

    relative_path = f"tmp/{user_id}/{uuid.uuid4().hex}{extension}"
    target = resolve_within_root(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return relative_path


def is_own_temp_path(temp_path: str, user_id: int) -> bool:
    """判断路径是否位于该用户的临时区（纯字符串校验，不落盘）。

    提交表单时先用它整体校验，避免部分文件已移动后才发现非法项。
    """
    return temp_path.strip().lstrip("/").startswith(f"tmp/{user_id}/")


def promote_temp(temp_path: str, user_id: int, kind: str) -> tuple[str, str]:
    """把临时文件移入正式区并生成缩略图，返回 (正式路径, 缩略图路径)。

    temp_path 必须位于该用户的临时区，否则拒绝——防止把他人临时文件认领进自己的记录。
    """
    normalized = temp_path.strip().lstrip("/")
    if not is_own_temp_path(temp_path, user_id):
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
    """生成最长边不超过 THUMB_MAX_EDGE 的 JPEG 缩略图（列表卡片用，避免加载原图）。

    第二道防线：正常情况下 save_temp 已验过内容，但临时文件在盘上仍可能被损坏，
    这里失败要转成业务错误（否则会以 500 冒出去，且文件已落在正式区）。
    """
    try:
        with Image.open(source) as image:
            converted = image.convert("RGB")
            converted.thumbnail((THUMB_MAX_EDGE, THUMB_MAX_EDGE))
            converted.save(target, "JPEG", quality=82)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("图片无法解码，请换一张重试") from exc


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
