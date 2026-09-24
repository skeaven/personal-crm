"""kinship 称谓引擎（D15）：角色路径 → 中文称呼 + 辈分差。

纯函数模块，无 IO 无状态（同 calendar.py 定位）。输入是"从'我'出发的每一跳
解析出的目标角色序列" [(kind, role), ...]，其中 kind ∈ 系统类型类别
（parent/spouse/sibling），role 是该跳目标节点相对当前节点的角色。

规则表只存事实映射（爸爸/爷爷/岳父…约 40 条 + sibling 长幼归一），
两级匹配：精确 → elder_/younger_ 前缀归一；都未命中返回 None，
由调用方退回旧的标签句式（旧数据 / 规则外组合不虚构称谓）。
"""

# 每一跳的形状：(系统类型类别, 目标角色)
KinshipStep = tuple[str, str]

# 角色值域（表单下拉与建边校验共用；语义：from 是 to 的 from_role）
ROLE_DOMAINS: dict[str, dict[str, tuple[str, ...]]] = {
    "parent": {"from": ("father", "mother"), "to": ("son", "daughter")},
    "spouse": {"from": ("husband", "wife", "partner"), "to": ("husband", "wife", "partner")},
    "sibling": {
        "from": ("elder_brother", "younger_brother", "elder_sister", "younger_sister"),
        "to": ("elder_brother", "younger_brother", "elder_sister", "younger_sister"),
    },
}

# 精确规则：路径（含长幼）→ 称呼
_EXACT_RULES: dict[tuple[KinshipStep, ...], str] = {
    # 一跳：直系/配偶/同胞
    (("parent", "father"),): "爸爸",
    (("parent", "mother"),): "妈妈",
    (("spouse", "husband"),): "丈夫",
    (("spouse", "wife"),): "妻子",
    (("spouse", "partner"),): "伴侣",
    (("sibling", "elder_brother"),): "哥哥",
    (("sibling", "younger_brother"),): "弟弟",
    (("sibling", "elder_sister"),): "姐姐",
    (("sibling", "younger_sister"),): "妹妹",
    (("parent", "son"),): "儿子",
    (("parent", "daughter"),): "女儿",
    # 二跳：祖辈（父系/母系）
    (("parent", "father"), ("parent", "father")): "爷爷",
    (("parent", "father"), ("parent", "mother")): "奶奶",
    (("parent", "mother"), ("parent", "father")): "外公",
    (("parent", "mother"), ("parent", "mother")): "外婆",
    # 二跳：父母旁系（伯/叔/姑/舅/姨）
    (("parent", "father"), ("sibling", "elder_brother")): "伯父",
    (("parent", "father"), ("sibling", "younger_brother")): "叔叔",
    (("parent", "father"), ("sibling", "elder_sister")): "姑姑",
    (("parent", "father"), ("sibling", "younger_sister")): "姑姑",
    (("parent", "mother"), ("sibling", "elder_brother")): "舅舅",
    (("parent", "mother"), ("sibling", "younger_brother")): "舅舅",
    (("parent", "mother"), ("sibling", "elder_sister")): "姨妈",
    (("parent", "mother"), ("sibling", "younger_sister")): "姨妈",
    # 二跳：配偶系直系（岳家/婆家）
    (("spouse", "wife"), ("parent", "father")): "岳父",
    (("spouse", "wife"), ("parent", "mother")): "岳母",
    (("spouse", "husband"), ("parent", "father")): "公公",
    (("spouse", "husband"), ("parent", "mother")): "婆婆",
    # 二跳：同辈姻亲（嫂/弟妹/姐夫/妹夫/儿媳/女婿）
    (("sibling", "elder_brother"), ("spouse", "wife")): "嫂子",
    (("sibling", "younger_brother"), ("spouse", "wife")): "弟妹",
    (("sibling", "elder_sister"), ("spouse", "husband")): "姐夫",
    (("sibling", "younger_sister"), ("spouse", "husband")): "妹夫",
    (("parent", "son"), ("spouse", "wife")): "儿媳",
    (("parent", "daughter"), ("spouse", "husband")): "女婿",
    # 二跳：孙辈（子系孙/女，女系加"外"）
    (("parent", "son"), ("parent", "son")): "孙子",
    (("parent", "son"), ("parent", "daughter")): "孙女",
    (("parent", "daughter"), ("parent", "son")): "外孙",
    (("parent", "daughter"), ("parent", "daughter")): "外孙女",
    # 二跳：侄甥（兄弟之子女=侄，姐妹之子女=外甥）
    (("sibling", "elder_brother"), ("parent", "son")): "侄子",
    (("sibling", "elder_brother"), ("parent", "daughter")): "侄女",
    (("sibling", "younger_brother"), ("parent", "son")): "侄子",
    (("sibling", "younger_brother"), ("parent", "daughter")): "侄女",
    (("sibling", "elder_sister"), ("parent", "son")): "外甥",
    (("sibling", "elder_sister"), ("parent", "daughter")): "外甥女",
    (("sibling", "younger_sister"), ("parent", "son")): "外甥",
    (("sibling", "younger_sister"), ("parent", "daughter")): "外甥女",
}

# 归一规则：sibling 的 elder_/younger_ 前缀剥掉后（长幼不影响称呼的条目）
_NORMALIZED_RULES: dict[tuple[KinshipStep, ...], str] = {
    (("parent", "father"), ("sibling", "brother")): "叔叔",  # 精确表已有伯/叔，归一兜底取叔
    (("parent", "father"), ("sibling", "sister")): "姑姑",
    (("parent", "mother"), ("sibling", "brother")): "舅舅",
    (("parent", "mother"), ("sibling", "sister")): "姨妈",
}


def _normalize_sibling_role(role: str) -> str:
    """剥掉 sibling 角色的长幼前缀（elder_sister→sister），其余原样。"""
    for prefix in ("elder_", "younger_"):
        if role.startswith(prefix):
            return role[len(prefix):]
    return role


def kinship_title(path: list[KinshipStep]) -> str | None:
    """把角色路径解析为中文称呼；空路径返回空串，规则外返回 None。

    匹配顺序：精确（保留长幼语义，如伯父/叔叔有别）→ sibling 长幼归一
    （姑/姨等称呼不分长幼的条目）。
    """
    if not path:
        return ""
    key = tuple(path)
    if key in _EXACT_RULES:
        return _EXACT_RULES[key]
    normalized = tuple((kind, _normalize_sibling_role(role)) for kind, role in path)
    return _NORMALIZED_RULES.get(normalized)


def generation_diff(path: list[KinshipStep]) -> int:
    """辈分差（相对"我"）：父系 +1、子系 -1、配偶/同辈 0，路径累加。"""
    diff = 0
    for _kind, role in path:
        if role in ("father", "mother"):
            diff += 1
        elif role in ("son", "daughter"):
            diff -= 1
    return diff
