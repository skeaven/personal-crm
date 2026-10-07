"""待办写工具执行器：确认队列的落库端。"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.registry import parse_iso_date
from app.modules.auth.models import User
from app.modules.records import service as records_service
from app.modules.records.schemas import TaskCreate


async def create_task(db: AsyncSession, user: User, payload: dict) -> dict:
    """执行建待办：contact_id 直传（可读性校验由 records service 兜底）、日期解析后落库。"""
    due_at = (
        datetime.combine(
            parse_iso_date(str(payload["due_at"]), "due_at"), datetime.min.time(), tzinfo=UTC
        )
        if payload.get("due_at")
        else None
    )
    task = await records_service.create_task(
        db, user, TaskCreate(
            title=str(payload["title"]),
            contact_id=payload.get("contact_id"),
            due_at=due_at,
        )
    )
    return {"ok": True, "message": f"待办已创建（id={task.id}）：{task.title}"}
