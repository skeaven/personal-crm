"""活动写工具执行器：确认队列的落库端。"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessError
from app.modules.ai.registry import parse_iso_date, resolve_contact_name
from app.modules.auth.models import User
from app.modules.records import service as records_service
from app.modules.records.schemas import ActivityCreate


async def create_activity(db: AsyncSession, user: User, payload: dict) -> dict:
    """执行记活动：参与者名逐个解析（不可读/不存在即失败并说明）。"""
    occurred = parse_iso_date(str(payload["occurred_at"]), "occurred_at")
    occurred_dt = datetime.combine(occurred, datetime.min.time(), tzinfo=UTC)

    participant_ids: list[int] = []
    for name in payload.get("participant_names", []):
        resolved = await resolve_contact_name(db, user, name)
        if resolved is None:
            raise BusinessError(f"没有找到参与者「{name}」，请先在名册中记录")
        participant_ids.append(resolved)

    activity = await records_service.create_activity(
        db, user, ActivityCreate(
            title=str(payload["title"]),
            occurred_at=occurred_dt,
            location=payload.get("location"),
            participant_ids=participant_ids,
        )
    )
    return {"ok": True, "message": f"活动已记录（id={activity.id}）：{activity.title}"}
