"""持久化 checkpointer 真库 smoke（spec §6：checkpointer 相关测试用测试库同一 PostgreSQL）。

生产路径用 AsyncPostgresSaver 落库；进程内 InMemorySaver 只服务降级/普通会话测试。
本文件直接对测试库操真库，验证写→复原→删的完整生命周期（重启存活性由落库保证）。
"""

import os
from contextlib import AsyncExitStack

import pytest

pytestmark = pytest.mark.asyncio

# 从 DATABASE_URL 派生 psycopg 连接串（去 +asyncpg 方言前缀），与生产 lifespan 同源
DSN = os.environ["DATABASE_URL"].replace("+asyncpg", "")
THREAD = "smoke:persist-probe"


@pytest.fixture
async def postgres_saver():
    """起一个真库 AsyncPostgresSaver，退出时关闭连接。"""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with AsyncExitStack() as stack:
        saver = await stack.enter_async_context(AsyncPostgresSaver.from_conn_string(DSN))
        await saver.setup()  # 幂等建表
        yield saver


async def _min_checkpoint() -> dict:
    """与 run 环境一致的最小 checkpoint 结构（空 messages 即可验证落库）。"""
    return {
        "v": 4,
        "id": "smoke-write-1",
        "ts": "2026-09-27T20:14:19.804150+00:00",
        "channel_values": {"messages": []},
        "channel_versions": {"__start__": 1, "messages": 1},
        "versions_seen": {"__input__": {}, "__start__": {"__start__": 1}},
    }


async def test_checkpointer_write_read_delete_roundtrip(postgres_saver):
    """写一个 checkpoint → 全新实例读回 → 删除线程后读不到（跨实例=跨进程存活性）。"""
    config = {"configurable": {"thread_id": THREAD, "checkpoint_ns": ""}}
    await postgres_saver.aput(
        config, await _min_checkpoint(),
        {"source": "input", "step": 0, "parents": {}}, {"__start__": 1, "messages": 1},
    )
    # 先保证写侧已落库（真库无内存缓存；连接关闭后由新实例读回即可证明）
    # 读回前先删掉本 fixture 的连接，等价于进程重启后重建连接
    del postgres_saver

    # 全新实例（等价后端进程重启后重新建连）
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with AsyncExitStack() as stack:
        saver2 = await stack.enter_async_context(AsyncPostgresSaver.from_conn_string(DSN))
        await saver2.setup()
        snap = await saver2.aget_tuple({"configurable": {"thread_id": THREAD}})
        assert snap is not None, "写后重启读不到 —— 持久化未生效"
        assert snap.checkpoint["id"] == "smoke-write-1"

        # 删除线程 → 再读应为 None
        await saver2.adelete_thread(THREAD)
        gone = await saver2.aget_tuple({"configurable": {"thread_id": THREAD}})
        assert gone is None, "adelete_thread 后线程仍可读 —— 删除未生效"