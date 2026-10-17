# Task 1: 数据库迁移 - 创建 spaces 表

## Goal
创建 `spaces` 表并添加 Space ORM 模型，实现空间化权限模型的基础数据结构。

## Files to Create/Modify
- Create: `backend/alembic/versions/XXXX_create_spaces_table.py`
- Modify: `backend/app/modules/auth/models.py` (添加 Space 模型)

## Interfaces
- **Consumes**: `families` 表, `users` 表
- **Produces**: `spaces` 表, `Space` ORM 模型

## Requirements

### 1. Space ORM 模型
在 `backend/app/modules/auth/models.py` 中添加：

```python
class Space(Base, TimestampMixin):
    """空间：数据归属的抽象层，shared（家庭共享）或 user（用户私有）。"""
    
    __tablename__ = "spaces"
    __table_args__ = (
        CheckConstraint(
            "(type = 'shared' AND family_id IS NOT NULL AND owner_user_id IS NULL) OR "
            "(type = 'user' AND owner_user_id IS NOT NULL AND family_id IS NULL)",
            name="check_space_type_consistency"
        ),
        UniqueConstraint("family_id", name="uq_shared_space_per_family", postgresql_where="type = 'shared'"),
        UniqueConstraint("owner_user_id", name="uq_user_space_per_user", postgresql_where="type = 'user'"),
    )
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False, comment="shared（家庭共享）/ user（用户私有）")
    family_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("families.id"), nullable=True, index=True, comment="共享空间所属家庭")
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True, index=True, comment="用户空间所有者")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="空间名称")
```

### 2. Alembic 迁移脚本
创建迁移脚本，包含：
- 创建 spaces 表（所有字段、约束、索引）
- 为每个家庭创建共享空间
- 为每个活跃用户创建用户空间
- 完整的回滚逻辑

### 3. 验证步骤
- 运行 `alembic upgrade head`
- 验证 spaces 表已创建
- 验证共享空间数量 = 家庭数量
- 验证用户空间数量 = 活跃用户数量

## Global Constraints
- Python >= 3.11
- SQLAlchemy >= 2.0
- 必须包含完整回滚逻辑
- 所有迁移必须幂等

## Success Criteria
1. Space 模型正确定义，包含所有约束
2. 迁移脚本成功执行
3. 数据正确初始化（每个家庭一个共享空间，每个用户一个用户空间）
4. 所有测试通过
5. Git commit 包含清晰的 commit message
