"""工具注册表契约测试：名字唯一、标签齐全、写工具与执行器一一对应。

这组断言的价值不在覆盖行为，而在**拦住静默失败**：
- 缺执行器的写工具，approve() 只会记 ok=False，用户看到的是"提议执行失败"
  而不是"系统缺实现"，排查成本极高；
- 缺 label 的工具，确认面板会显示英文原名；
- 名字不合约定会让模型在 52 个工具里选错。
"""

import pytest

from app.modules.ai import registry
from app.modules.ai.pending import EXECUTORS

pytestmark = pytest.mark.asyncio

# 动词表：新增工具必须以此表之一开头
VERBS = ("list", "get", "create", "update", "delete", "promote", "convert", "mark")

# 历史命名不遵循动词表，冻结在此；新增工具不得再进这个集合。
# Task 7 删除 search_contacts 时，同步把它从本集合移除。
LEGACY_NAMES = {"kinship_of", "semantic_search", "search_contacts"}


def test_tool_names_are_unique():
    """工具名唯一：MCP 注册与 pending_actions.tool_name 都按名字寻址。"""
    names = [tool.name for tool in registry.ALL_TOOLS]
    assert len(names) == len(set(names)), f"重复的工具名：{sorted(names)}"


def test_every_tool_has_label_and_description():
    """每个工具都有中文名与非空描述：前者供确认面板，后者是模型选择工具的唯一依据。"""
    offenders = [
        tool.name
        for tool in registry.ALL_TOOLS
        if not tool.label.strip() or not tool.description.strip()
    ]
    assert offenders == [], f"以下工具缺 label 或 description：{offenders}"


def test_tool_names_follow_verb_entity_convention():
    """新工具名必须是 <动词>_<实体>；历史命名走白名单，不许再扩大。"""
    offenders = [
        tool.name
        for tool in registry.ALL_TOOLS
        if tool.name not in LEGACY_NAMES and tool.name.split("_")[0] not in VERBS
    ]
    assert offenders == [], f"以下工具名不符合 <动词>_<实体>：{offenders}"


def test_write_tools_exactly_match_executors():
    """写工具的集合与执行器表完全相等（双向差集为空）。

    单向断言会漏掉另一半问题：多出的执行器是死代码，
    任何工具改名都会留下它，且不会有任何测试发现。
    """
    write_tools = {tool.name for tool in registry.ALL_TOOLS if tool.risk == "write_queue"}
    assert write_tools - set(EXECUTORS) == set(), "以下写工具没有执行器"
    assert set(EXECUTORS) - write_tools == set(), "以下执行器没有对应的写工具"


def test_read_tools_have_no_executor():
    """读工具直执行，不进确认队列，因此不该有执行器。"""
    read_tools = {tool.name for tool in registry.ALL_TOOLS if tool.risk == "read"}
    assert read_tools & set(EXECUTORS) == set(), "读工具不该有执行器"


def test_every_args_schema_serializes_to_json_schema():
    """每个入参 schema 都能产出 JSON schema：MCP 注册与 agent 绑定的前提。"""
    for tool in registry.ALL_TOOLS:
        schema = tool.args_schema.model_json_schema()
        assert "properties" in schema or schema.get("type") == "object", (
            f"{tool.name} 的 schema 不是对象类型"
        )
