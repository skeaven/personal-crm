"""uploads 模块 API：临时区上传与本人读取。

鉴权边界：临时文件只有上传者本人能读；提交进业务记录后，改由各业务模块
（如 records 的活动图片端点）按业务可见性判权。
"""

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import get_current_user
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
