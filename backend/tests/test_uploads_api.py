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
    user, _ = await make_user(username="uploader", password="pw12345678")
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
    await make_user(username="reader", password="pw12345678")
    headers = await login_headers("reader", "pw12345678")
    temp_path = (
        await client.post("/api/v1/uploads/temp", files=_image_upload(), headers=headers)
    ).json()["temp_path"]

    response = await client.get(f"/api/v1/uploads/{temp_path}", headers=headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


async def test_read_other_users_temp_image_is_404(client, login_headers, make_user):
    """他人的临时文件一律 404（不泄露存在性）。"""
    await make_user(username="owner_a", password="pw12345678")
    await make_user(username="owner_b", password="pw12345678")
    headers_a = await login_headers("owner_a", "pw12345678")
    headers_b = await login_headers("owner_b", "pw12345678")
    temp_path = (
        await client.post("/api/v1/uploads/temp", files=_image_upload(), headers=headers_a)
    ).json()["temp_path"]

    response = await client.get(f"/api/v1/uploads/{temp_path}", headers=headers_b)

    assert response.status_code == 404
