"""funds 模块测试：资金往来 CRUD、方向/类别/状态过滤、结清流转、D7 隔离。"""

import pytest

from tests.factories import (
    create_contact_for,
    create_family_user,
    create_fund_for,
)

pytestmark = pytest.mark.asyncio


async def test_create_fund_loan_defaults(client, make_user, login_headers):
    """创建借款：带 due_at 自动置 pending；不带则 status 为空（不涉及结清）。"""
    demo, _ = await make_user(username="demo")
    friend = await create_contact_for(demo, last_name="李", first_name="娜")
    headers = await login_headers("demo", "demo12345")

    loan = await client.post(
        "/api/v1/funds",
        json={
            "contact_id": friend.id,
            "direction": "out",
            "category": "loan",
            "amount": "2000.00",
            "occurred_at": "2026-09-01",
            "due_at": "2026-10-01",
            "description": "急用周转",
        },
        headers=headers,
    )
    assert loan.status_code == 200, loan.text
    body = loan.json()
    assert body["status"] == "pending" and body["settled_at"] is None
    assert body["amount"] == "2000.00" and body["currency"] == "CNY"

    gift_money = await client.post(
        "/api/v1/funds",
        json={
            "contact_id": friend.id,
            "direction": "out",
            "category": "gift_money",
            "amount": "800.00",
            "occurred_at": "2026-09-15",
        },
        headers=headers,
    )
    assert gift_money.status_code == 200
    assert gift_money.json()["status"] is None


async def test_fund_list_filters_and_search(client, make_user, login_headers):
    """资金列表：direction/category/status 过滤 + 说明关键字搜索。"""
    demo, _ = await make_user(username="demo")
    friend = await create_contact_for(demo, last_name="李", first_name="娜")
    await create_fund_for(
        demo, contact_id=friend.id, direction="out", category="loan", amount=2000,
        occurred_at="2026-09-01", due_at="2026-10-01", status="pending", description="婚礼随礼备用",
    )
    await create_fund_for(
        demo, contact_id=friend.id, direction="in", category="repayment", amount=1000,
        occurred_at="2026-09-10", status="settled",
    )
    await create_fund_for(
        demo, direction="out", category="gift_money", amount=800,
        occurred_at="2026-09-15", description="满月酒礼金",
    )
    headers = await login_headers("demo", "demo12345")

    pending = (await client.get("/api/v1/funds?status=pending", headers=headers)).json()
    assert len(pending) == 1 and pending[0]["category"] == "loan"

    flow_in = (await client.get("/api/v1/funds?direction=in", headers=headers)).json()
    assert len(flow_in) == 1 and flow_in[0]["category"] == "repayment"

    searched = (await client.get("/api/v1/funds?search=礼金", headers=headers)).json()
    assert len(searched) == 1 and searched[0]["description"] == "满月酒礼金"


async def test_fund_settle_flow(client, make_user, login_headers):
    """结清流转：置 settled 自动盖 settled_at；改回 pending 时清空结清日。"""
    demo, _ = await make_user(username="demo")
    fund = await create_fund_for(
        demo, direction="out", category="loan", amount=2000,
        occurred_at="2026-09-01", due_at="2026-10-01", status="pending",
    )
    headers = await login_headers("demo", "demo12345")

    settled = await client.patch(
        f"/api/v1/funds/{fund.id}", json={"status": "settled"}, headers=headers
    )
    assert settled.status_code == 200
    assert settled.json()["settled_at"] is not None

    reopened = await client.patch(
        f"/api/v1/funds/{fund.id}", json={"status": "pending"}, headers=headers
    )
    assert reopened.status_code == 200
    assert reopened.json()["settled_at"] is None


async def test_fund_visibility_isolation_and_permissions(client, make_user, login_headers):
    """D7：私密流水对家人不可见；家人可读不可写；所有者可删。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    family_fund = await create_fund_for(
        demo, direction="out", category="loan", amount=100,
        occurred_at="2026-09-01", visibility="family",
    )
    private_fund = await create_fund_for(
        demo, direction="in", category="other", amount=50,
        occurred_at="2026-09-02", visibility="private",
    )
    tong_headers = await login_headers("tong", "demo12345")

    listed = (await client.get("/api/v1/funds", headers=tong_headers)).json()
    assert [f["id"] for f in listed] == [family_fund.id]

    forbidden = await client.patch(
        f"/api/v1/funds/{family_fund.id}", json={"status": "settled"}, headers=tong_headers
    )
    assert forbidden.status_code == 403
    hidden = await client.get(f"/api/v1/funds/{private_fund.id}", headers=tong_headers)
    assert hidden.status_code == 404

    owner_headers = await login_headers("demo", "demo12345")
    deleted = await client.delete(f"/api/v1/funds/{family_fund.id}", headers=owner_headers)
    assert deleted.status_code == 204
