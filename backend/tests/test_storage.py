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


def _jpeg_bytes(size: tuple[int, int] = (1200, 800)) -> bytes:
    """生成一张指定尺寸的 JPEG 字节流（缩略图用例需要真实可解码的图片）。"""
    import io

    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, "JPEG")
    return buffer.getvalue()


def _write_fake_image(user_id: int, name: str = "pic.jpg") -> str:
    """造一张真实的小 JPEG 放进临时区，返回其相对路径。"""
    return storage.save_temp(user_id, name, _jpeg_bytes())


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


def test_save_temp_rejects_non_image_content():
    """扩展名伪装成图片的非图片内容必须在上传入口被拒。

    iPhone 直出的 HEIC 改名成 .jpg 是很常见的路径，而扩展名校验拦不住它；
    若放行，promotion 阶段会抛 UnidentifiedImageError（非 BusinessError → 500），
    且文件已被搬进正式区成为永不被回收的孤儿。
    """
    with pytest.raises(ValidationError):
        storage.save_temp(1, "fake.jpg", b"this is not an image")


def test_save_temp_rejects_truncated_jpeg():
    """截断/损坏的 JPEG 同样必须被拒（真实 JPEG 头 + 残缺数据）。"""
    truncated = _jpeg_bytes((40, 40))[: len(_jpeg_bytes((40, 40))) // 3]

    with pytest.raises(ValidationError):
        storage.save_temp(1, "broken.jpg", truncated)


async def test_app_startup_cleans_temp(monkeypatch):
    """应用启动时必须调用一次临时区清理。

    spec 3.1 写明「应用启动时执行一次」，否则用户上传后点取消留下的文件、
    以及各种失败路径的残留，在自托管场景下永远没有回收路径。
    """
    from app.services import storage as storage_module

    calls: list[int] = []
    monkeypatch.setattr(
        storage_module, "cleanup_temp", lambda *args, **kwargs: calls.append(1) or 0
    )

    from app.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        pass

    assert calls, "启动时没有调用 storage.cleanup_temp"


def test_resolve_own_temp_rejects_sibling_temp_area():
    """两层 .. 能留在 upload 根内却指向他人临时区——判权必须落在解析后的真实路径上。

    is_own_temp_path 只是字符串前缀，resolve_within_root 只管「不逃出 upload 根」，
    中间那层「不得逃出本人 tmp 子目录」得由 resolve_own_temp 自己守。
    """
    with pytest.raises(ValidationError):
        storage.resolve_own_temp("tmp/7/../../tmp/8/a.png", user_id=7)


def test_promote_temp_rejects_sibling_temp_path():
    """同源写缺口：两层 .. 留在 upload 根内却指向他人临时区 → 必须被拒。

    样本用真实存在的他人临时文件：否则「文件不存在」先抛，测不到防线本身。
    """
    victim = _write_fake_image(8)

    with pytest.raises(ValidationError):
        storage.promote_temp(f"tmp/7/../../{victim}", user_id=7, kind="activities")
