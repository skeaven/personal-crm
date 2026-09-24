"""联系人位置链路测试（D14）：创建/更新解析坐标缓存、变更才重算、地图聚合。"""

import pytest

from app.modules.contacts import service as contact_service
from app.modules.contacts.schemas import ContactCreate, ContactUpdate
from tests.factories import create_contact_for

pytestmark = pytest.mark.asyncio


async def _amap_key(db_session, demo):
    """复用服务层私有读取（仅测试断言用）：未配置时为 None。"""
    return await contact_service._load_amap_key(db_session)


async def test_create_with_location_resolves_static(db_session, make_user):
    """创建带 location 的联系人：静态表解析坐标与省份（无 key 默认链路）。"""
    demo, _ = await make_user(username="demo")
    created = await contact_service.create_contact(
        db_session,
        demo,
        ContactCreate(last_name="王", first_name="小明", location="浙江省杭州市"),
    )
    contact = created.contact
    assert contact is not None
    assert contact.location == "浙江省杭州市"
    assert contact.location_source == "static"
    assert 119.0 < contact.location_lng < 121.0
    assert 29.0 < contact.location_lat < 31.0
    assert contact.location_province == "浙江省"


async def test_create_without_location_keeps_null(db_session, make_user):
    """不带 location：缓存列全空（不误报"未解析"）。"""
    demo, _ = await make_user(username="demo")
    created = await contact_service.create_contact(
        db_session, demo, ContactCreate(last_name="李", first_name="四")
    )
    contact = created.contact
    assert contact.location is None
    assert contact.location_source is None
    assert contact.location_lng is None


async def test_update_location_recomputes_and_clear(db_session, make_user):
    """更新 location：变更重算（换成区级）；清空时缓存列一并清空。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, first_name="阿", last_name="芳")

    updated = await contact_service.update_contact(
        db_session,
        demo,
        contact.id,
        ContactUpdate(location="上海市浦东新区"),
    )
    assert updated.location_source == "static"
    assert updated.location_province == "上海市"
    assert 30.5 < updated.location_lat < 32.0

    cleared = await contact_service.update_contact(
        db_session, demo, contact.id, ContactUpdate(location=None)
    )
    assert cleared.location is None
    assert cleared.location_source is None
    assert cleared.location_lng is None


async def test_update_same_location_skips_resolve(monkeypatch, db_session, make_user):
    """location 未变更：不触发解析（省外部调用配额）。"""
    demo, _ = await make_user(username="demo")
    created = await contact_service.create_contact(
        db_session, demo, ContactCreate(last_name="赵", first_name="敏", location="北京市")
    )
    contact_id = created.contact.id

    called = []

    async def spy_resolve(text, *, amap_key=None):
        called.append(text)
        return None

    monkeypatch.setattr(contact_service, "resolve_location", spy_resolve)
    await contact_service.update_contact(
        db_session, demo, contact_id, ContactUpdate(location="北京市")
    )
    assert called == []


async def test_unresolvable_location_marks_none(db_session, make_user):
    """解析未命中：source=none、坐标为空，location 文本保留。"""
    demo, _ = await make_user(username="demo")
    created = await contact_service.create_contact(
        db_session, demo, ContactCreate(last_name="钱", first_name="图", location="火星乌托邦")
    )
    contact = created.contact
    assert contact.location == "火星乌托邦"
    assert contact.location_source == "none"
    assert contact.location_lng is None


async def test_map_points_aggregates_province(db_session, make_user):
    """地图数据：仅含坐标点，省份计数倒序。"""
    demo, _ = await make_user(username="demo")
    await contact_service.create_contact(
        db_session, demo, ContactCreate(last_name="孙", first_name="一", location="杭州市")
    )
    await contact_service.create_contact(
        db_session, demo, ContactCreate(last_name="周", first_name="二", location="宁波市")
    )
    await contact_service.create_contact(
        db_session, demo, ContactCreate(last_name="吴", first_name="三", location="火星乌托邦")
    )
    result = await contact_service.map_points(db_session, demo)
    assert len(result.points) == 2
    assert {p.display_name for p in result.points} == {"孙一", "周二"}
    assert result.provinces[0].name == "浙江省"
    assert result.provinces[0].count == 2
