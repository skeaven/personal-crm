"""迁移链完整性（D23 补）：其余后端测试走 `Base.metadata.create_all` 建表，迁移不进覆盖面。

提交进仓库的迁移必须自洽——`down_revision` 指向的 revision 必须在仓库里真实存在。
D23 曾把 down_revision 指向一个只存在于工作区、从未提交的迁移 id，结果任何干净检出
执行 alembic 命令都抛 `KeyError`，而全部单测照样绿。这两条断言就是那次缺口的常设补丁。
"""

import re
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

# 相对测试文件解析，pytest 从 backend/ 或仓库根目录启动都能跑
BACKEND_DIR = Path(__file__).resolve().parents[1]

# 引号两种都要认：alembic 模板默认单引号（`revision: str = 'abc'`），
# 手写或新模板可能是双引号——只认一种会误报缺失。
_QUOTED = r"""['\"]([^'\"]+)['\"]"""
_REVISION = re.compile(rf"^revision(?:\s*:\s*[^=]+)?\s*=\s*{_QUOTED}", re.MULTILINE)
_DOWN_REVISION = re.compile(rf"^down_revision(?:\s*:\s*[^=]+)?\s*=\s*{_QUOTED}", re.MULTILINE)


def test_migration_graph_resolves_to_single_head():
    """整条链可解析且只有一个 head（缺失的 down_revision 会在这里抛 KeyError）。"""
    script = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1, f"应只有一个 head，实得 {heads}"
    for head in heads:
        assert list(script.walk_revisions(base="base", head=head)), f"{head} 回溯不到 base"


def test_referenced_down_revisions_all_exist():
    """逐个文件核对：down_revision 必须指向仓库里真实存在的迁移（不依赖 alembic 解析）。

    独立的静态核对——链断了也能报出到底缺哪个 id，而不是只抛 KeyError。
    """
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in sorted((BACKEND_DIR / "alembic" / "versions").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        found = _REVISION.search(text)
        if found:
            revisions.add(found.group(1))
        found = _DOWN_REVISION.search(text)
        if found:
            parents.add(found.group(1))

    missing = sorted(parents - revisions)
    assert missing == [], f"down_revision 指向仓库里不存在的迁移：{missing}"
