"""分页契约测试：默认 20、上限截断、offset 翻页、X-Total-Count。"""

from datetime import date
from decimal import Decimal

import pytest

PAGED_ENDPOINTS = [
    ("activities", "/api/v1/records/activities"),
    ("gifts", "/api/v1/gifts"),
    ("funds", "/api/v1/funds"),
]


async def _seed(db, user, kind: str, count: int) -> None:
    """按记录类型造 count 条数据。

    必须落到已提交状态——db_session 与 HTTP 请求（get_db）是两个独立会话，
    未提交的数据对端点不可见。gifts/funds 经 factories 造数（内部自行 commit）。
    """
    from tests.factories import create_fund_for, create_gift_for

    if kind == "activities":
        from app.modules.records.models import Activity

        for index in range(count):
            db.add(
                Activity(
                    title=f"活动{index:02d}",
                    owner_user_id=user.id,
                    family_id=user.family_id,
                )
            )
        await db.commit()
        return

    for index in range(count):
        if kind == "gifts":
            await create_gift_for(user, direction="given", title=f"礼物{index:02d}")
        else:
            await create_fund_for(
                user,
                direction="out",
                category="loan",
                amount=Decimal("1.00"),
                occurred_at=date.today(),
            )


@pytest.mark.parametrize("kind,endpoint", PAGED_ENDPOINTS)
async def test_pagination_defaults_to_20(
    kind, endpoint, client, login_headers, make_user, db_session
):
    """不传 limit 时最多返回 20 条（不存在"不传即全量"的旁路）。"""
    user, _ = await make_user(username=f"pager_{kind}", password="pw12345678")
    headers = await login_headers(f"pager_{kind}", "pw12345678")
    await _seed(db_session, user, kind, 25)

    response = await client.get(endpoint, headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 20


@pytest.mark.parametrize("kind,endpoint", PAGED_ENDPOINTS)
async def test_pagination_returns_total_count(
    kind, endpoint, client, login_headers, make_user, db_session
):
    """X-Total-Count 反映总数而非本页条数（列表页页码靠它算）。"""
    user, _ = await make_user(username=f"counter_{kind}", password="pw12345678")
    headers = await login_headers(f"counter_{kind}", "pw12345678")
    await _seed(db_session, user, kind, 25)

    response = await client.get(endpoint, headers=headers)

    assert response.headers["X-Total-Count"] == "25"


@pytest.mark.parametrize("kind,endpoint", PAGED_ENDPOINTS)
async def test_pagination_limit_is_capped(kind, endpoint, client, login_headers, make_user):
    """limit 超过 200 被拒（防 limit=999999 绕过保护）。"""
    await make_user(username=f"capper_{kind}", password="pw12345678")
    headers = await login_headers(f"capper_{kind}", "pw12345678")

    response = await client.get(f"{endpoint}?limit=999999", headers=headers)

    assert response.status_code == 422


@pytest.mark.parametrize("kind,endpoint", PAGED_ENDPOINTS)
async def test_offset_pages_do_not_overlap(
    kind, endpoint, client, login_headers, make_user, db_session
):
    """offset 翻页不重不漏（无日期记录稳定排末尾，见 Review Focus #3）。"""
    user, _ = await make_user(username=f"flip_{kind}", password="pw12345678")
    headers = await login_headers(f"flip_{kind}", "pw12345678")
    await _seed(db_session, user, kind, 25)

    first = (await client.get(f"{endpoint}?limit=20&offset=0", headers=headers)).json()
    second = (await client.get(f"{endpoint}?limit=20&offset=20", headers=headers)).json()

    first_ids = {item["id"] for item in first}
    second_ids = {item["id"] for item in second}
    assert len(first_ids & second_ids) == 0
    assert len(first_ids | second_ids) == 25


async def test_offset_beyond_total_returns_empty(client, login_headers, make_user, db_session):
    """offset 超出总数返回空数组而不是报错（列表页翻到边界时的容错）。"""
    user, _ = await make_user(username="far_pager", password="pw12345678")
    headers = await login_headers("far_pager", "pw12345678")
    await _seed(db_session, user, "activities", 3)

    response = await client.get(
        "/api/v1/records/activities?limit=20&offset=100", headers=headers
    )

    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["X-Total-Count"] == "3"


async def test_pending_view_pagination_is_deterministic(
    client, login_headers, make_user, db_session
):
    """未结清视图（按应还日升序）分页必须是确定序。

    pending 分支原先只按 due_at 排序、没有唯一兜底键；due_at 并列时 Postgres
    不保证稳定顺序，LIMIT/OFFSET 跨页就有重复/遗漏的空间（Review Focus #3）。
    这里全部记录同为一天到期，并列组内必须按 id 递减，分页才可预测。
    """
    from tests.factories import create_fund_for

    user, _ = await make_user(username="pending_pager", password="pw12345678")
    headers = await login_headers("pending_pager", "pw12345678")
    for _ in range(25):
        await create_fund_for(
            user,
            direction="out",
            category="loan",
            amount=Decimal("1.00"),
            occurred_at=date.today(),
            due_at=date(2026, 12, 31),
            status="pending",
        )

    first = (
        await client.get("/api/v1/funds?status=pending&limit=20&offset=0", headers=headers)
    ).json()
    second = (
        await client.get("/api/v1/funds?status=pending&limit=20&offset=20", headers=headers)
    ).json()

    first_ids = [item["id"] for item in first]
    second_ids = [item["id"] for item in second]
    assert len(set(first_ids) & set(second_ids)) == 0, "跨页出现重复记录"
    assert len(set(first_ids) | set(second_ids)) == 25, "跨页出现遗漏"
    # 并列组内按 id 递减（唯一兜底键），分页才是确定序
    assert first_ids == sorted(first_ids, reverse=True), "首页未按 id 递减"
    assert second_ids == sorted(second_ids, reverse=True), "次页未按 id 递减"
    assert first_ids[-1] > second_ids[0], "跨页未按 id 接续"
