"""kinship 称谓引擎测试（D15）：角色路径 → 中文称呼 + 辈分差。

路径元素格式 (kind, role)，即每一跳解析出的"目标节点是当前节点的什么"。
用例基线 = 用户提供的参考方案（2026-09-22）全部示例 + 常见扩展。
"""

import pytest

from app.modules.graph import kinship

pytestmark = pytest.mark.asyncio


def test_direct_line_parents():
    """直系上一代：父母。"""
    assert kinship.kinship_title([("parent", "father")]) == "爸爸"
    assert kinship.kinship_title([("parent", "mother")]) == "妈妈"


def test_grandparents_paternal_maternal():
    """祖辈：父系/母系区分（爷爷/奶奶/外公/外婆）。"""
    assert kinship.kinship_title([("parent", "father"), ("parent", "father")]) == "爷爷"
    assert kinship.kinship_title([("parent", "father"), ("parent", "mother")]) == "奶奶"
    assert kinship.kinship_title([("parent", "mother"), ("parent", "father")]) == "外公"
    assert kinship.kinship_title([("parent", "mother"), ("parent", "mother")]) == "外婆"


def test_parent_siblings_uncles_aunts():
    """父母旁系：伯父/叔叔/姑姑/舅舅/姨妈（长幼与父系母系联动）。"""
    assert kinship.kinship_title([("parent", "father"), ("sibling", "elder_brother")]) == "伯父"
    assert kinship.kinship_title([("parent", "father"), ("sibling", "younger_brother")]) == "叔叔"
    assert kinship.kinship_title([("parent", "father"), ("sibling", "elder_sister")]) == "姑姑"
    assert kinship.kinship_title([("parent", "father"), ("sibling", "younger_sister")]) == "姑姑"
    assert kinship.kinship_title([("parent", "mother"), ("sibling", "elder_brother")]) == "舅舅"
    assert kinship.kinship_title([("parent", "mother"), ("sibling", "younger_brother")]) == "舅舅"
    assert kinship.kinship_title([("parent", "mother"), ("sibling", "elder_sister")]) == "姨妈"
    assert kinship.kinship_title([("parent", "mother"), ("sibling", "younger_sister")]) == "姨妈"


def test_spouse_in_laws():
    """配偶系：岳父岳母/公公婆婆（材料核心场景）。"""
    assert kinship.kinship_title([("spouse", "wife"), ("parent", "father")]) == "岳父"
    assert kinship.kinship_title([("spouse", "wife"), ("parent", "mother")]) == "岳母"
    assert kinship.kinship_title([("spouse", "husband"), ("parent", "father")]) == "公公"
    assert kinship.kinship_title([("spouse", "husband"), ("parent", "mother")]) == "婆婆"


def test_spouse_and_children():
    """配偶与子女。"""
    assert kinship.kinship_title([("spouse", "husband")]) == "丈夫"
    assert kinship.kinship_title([("spouse", "wife")]) == "妻子"
    assert kinship.kinship_title([("spouse", "partner")]) == "伴侣"
    assert kinship.kinship_title([("parent", "son")]) == "儿子"
    assert kinship.kinship_title([("parent", "daughter")]) == "女儿"


def test_siblings_with_order():
    """兄弟姐妹：长幼角色直接进称呼。"""
    assert kinship.kinship_title([("sibling", "elder_brother")]) == "哥哥"
    assert kinship.kinship_title([("sibling", "younger_brother")]) == "弟弟"
    assert kinship.kinship_title([("sibling", "elder_sister")]) == "姐姐"
    assert kinship.kinship_title([("sibling", "younger_sister")]) == "妹妹"


def test_in_law_spouses_of_siblings():
    """姻亲：嫂子/弟妹/姐夫/妹夫、儿媳/女婿。"""
    assert kinship.kinship_title([("sibling", "elder_brother"), ("spouse", "wife")]) == "嫂子"
    assert kinship.kinship_title([("sibling", "younger_brother"), ("spouse", "wife")]) == "弟妹"
    assert kinship.kinship_title([("sibling", "elder_sister"), ("spouse", "husband")]) == "姐夫"
    assert kinship.kinship_title([("sibling", "younger_sister"), ("spouse", "husband")]) == "妹夫"
    assert kinship.kinship_title([("parent", "son"), ("spouse", "wife")]) == "儿媳"
    assert kinship.kinship_title([("parent", "daughter"), ("spouse", "husband")]) == "女婿"


def test_grandchildren():
    """孙辈：子系孙/孙女，女系外孙/外孙女。"""
    assert kinship.kinship_title([("parent", "son"), ("parent", "son")]) == "孙子"
    assert kinship.kinship_title([("parent", "son"), ("parent", "daughter")]) == "孙女"
    assert kinship.kinship_title([("parent", "daughter"), ("parent", "son")]) == "外孙"
    assert kinship.kinship_title([("parent", "daughter"), ("parent", "daughter")]) == "外孙女"


def test_niblings():
    """侄甥：兄弟之子=侄子/侄女，姐妹之子=外甥/外甥女。"""
    assert kinship.kinship_title([("sibling", "elder_brother"), ("parent", "son")]) == "侄子"
    assert kinship.kinship_title([("sibling", "younger_brother"), ("parent", "daughter")]) == "侄女"
    assert kinship.kinship_title([("sibling", "elder_sister"), ("parent", "son")]) == "外甥"
    assert kinship.kinship_title(
        [("sibling", "younger_sister"), ("parent", "daughter")]
    ) == "外甥女"


def test_generation_diff():
    """辈分差：父 +1、子 -1、配偶与同辈 0，路径累加。"""
    assert kinship.generation_diff([("parent", "father")]) == 1
    assert kinship.generation_diff([("parent", "father"), ("parent", "father")]) == 2
    assert kinship.generation_diff([("parent", "son")]) == -1
    assert kinship.generation_diff([("spouse", "wife")]) == 0
    assert kinship.generation_diff([("sibling", "elder_brother")]) == 0
    assert kinship.generation_diff([("spouse", "wife"), ("parent", "father")]) == 1


def test_fallback_unmatched_path():
    """规则外路径：精确与归一两级匹配都未命中 → None（调用方退回兼容句式）。"""
    assert kinship.kinship_title([]) == ""
    triple = [("parent", "father"), ("sibling", "elder_brother"), ("spouse", "wife")]
    assert kinship.kinship_title(triple) is None
