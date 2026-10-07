"""写工具执行器：'工具名 → 落库函数' 的唯一映射（D11 确认队列的落库端）。

按模块分文件，与 registry 的工具分组一一对应。待办/活动/联系人之外的模块
（礼物、资金、关系图、提醒）在本轮后续阶段往这里加文件。
"""

from app.modules.ai.executors.activities import create_activity
from app.modules.ai.executors.contacts import (
    add_important_date,
    create_contact,
    delete_contact,
    delete_important_date,
    promote_contact,
    update_contact,
    update_important_date,
)
from app.modules.ai.executors.tasks import create_task

EXECUTORS = {
    "create_task": create_task,
    "create_activity": create_activity,
    "create_contact": create_contact,
    "update_contact": update_contact,
    "delete_contact": delete_contact,
    "promote_contact": promote_contact,
    "add_important_date": add_important_date,
    "update_important_date": update_important_date,
    "delete_important_date": delete_important_date,
}
