"""视觉导入测试：图片校验、多模态消息、视觉降级。

用一张真实的 1x1 PNG 做夹具——save_temp 有 _ensure_decodable 内容校验，
假字节流过不了上传，这是既有防线的正确行为，测试必须顺着它。
"""

import base64

import pytest
from httpx import AsyncClient

from tests.factories import login_as

pytestmark = pytest.mark.asyncio

# 1x1 透明 PNG（标准 base64），可解码、体积最小
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def _upload_image(client: AsyncClient, headers: dict, filename: str = "card.png") -> str:
    """经上传端点把 1x1 PNG 存进本人临时区，返回 temp_path。"""
    response = await client.post(
        "/api/v1/uploads/temp",
        files={"file": (filename, PNG_1PX, "image/png")},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["temp_path"]


async def test_chat_with_other_users_image_is_404(client, make_user):
    """冒用他人临时图必须 404（同家庭也不行——临时文件是账号私产）。"""
    owner, _ = await make_user(username="owner", password="pw12345678")
    owner_headers = await login_as(client, "owner", "pw12345678")
    temp_path = await _upload_image(client, owner_headers)

    await make_user(username="other", password="pw12345678", family_id=owner.family_id)
    other_headers = await login_as(client, "other", "pw12345678")

    response = await client.post(
        "/api/v1/ai/chat",
        json={"message": "存下名片", "images": [temp_path]},
        headers=other_headers,
    )
    assert response.status_code == 404


async def test_chat_with_escape_path_is_422(client, make_user):
    """`../` 穿越能骗过字符串前缀归属检查，resolve_within_root 必须拦下。"""
    demo, _ = await make_user(username="demo")
    headers = await login_as(client, "demo", "demo12345")

    response = await client.post(
        "/api/v1/ai/chat",
        # 路径带本人 id 通过归属前缀，再用 ../ 逃出临时区
        # 三层 ../ 才真正逃出临时区（两层恰好退回根目录内，本就不该拦）
        json={"message": "存下名片", "images": [f"tmp/{demo.id}/../../../secret.png"]},
        headers=headers,
    )
    assert response.status_code == 422


async def test_chat_with_missing_image_is_404(client, make_user):
    """自己临时区里不存在的路径（已过期被清理）→ 404，提示重传。"""
    demo, _ = await make_user(username="demo")
    headers = await login_as(client, "demo", "demo12345")

    response = await client.post(
        "/api/v1/ai/chat",
        json={"message": "存下名片", "images": [f"tmp/{demo.id}/deadbeef.png"]},
        headers=headers,
    )
    assert response.status_code == 404


async def test_chat_rejects_two_images(client, make_user):
    """契约层限 1 张：两张图直接 422（不到业务层）。"""
    await make_user(username="demo")
    headers = await login_as(client, "demo", "demo12345")

    response = await client.post(
        "/api/v1/ai/chat",
        json={"message": "存下名片", "images": ["tmp/1/a.png", "tmp/1/b.png"]},
        headers=headers,
    )
    assert response.status_code == 422
