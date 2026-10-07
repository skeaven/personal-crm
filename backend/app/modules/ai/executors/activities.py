"""活动写工具执行器：确认队列的落库端。"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.registry import parse_iso_date
from app.modules.auth.models import User
from app.modules.records import service as records_service
from app.modules.records.schemas import ActivityCreate


async def create_activity(db: AsyncSession, user: User, payload: dict) -> dict:
    """执行记活动：participant_ids 直传给 records service（不可读的参与者由它整体拒绝）。"""
    occurred = parse_iso_date(str(payload["occurred_at"]), "occurred_at")
    occurred_dt = datetime.combine(occurred, datetime.min.time(), tzinfo=UTC)

    activity = await records_service.create_activity(
        db, user, ActivityCreate(
            title=str(payload["title"]),
            occurred_at=occurred_dt,
            location=payload.get("location"),
            participant_ids=payload.get("participant_ids", []),
        )
    )
    return {"ok": True, "message": f"活动已记录（id={activity.id}）：{activity.title}"}
