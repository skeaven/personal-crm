"""模型聚合入口：import 全部模型模块，确保 Base.metadata 注册完整。

仅 Alembic env.py 与测试夹具需要导入本包；业务代码直接从各模块 models 导入。
"""

from app.core.db import Base  # noqa: F401
from app.core.models import ActivationMixin, OwnershipMixin, TimestampMixin  # noqa: F401
from app.modules.ai.models import AiSession, Embedding, PendingAction  # noqa: F401
from app.modules.auth.models import Family, User, UserToken  # noqa: F401
from app.modules.contacts.models import Contact, ImportantDate  # noqa: F401
from app.modules.funds.models import FundFlow  # noqa: F401
from app.modules.gifts.models import Gift, WishlistItem  # noqa: F401
from app.modules.graph.models import Relationship, RelationshipType  # noqa: F401
from app.modules.records.models import (  # noqa: F401
    Activity,
    ActivityImage,
    ActivityParticipant,
    Note,
    Task,
)
from app.modules.settings.models import AppSetting  # noqa: F401
