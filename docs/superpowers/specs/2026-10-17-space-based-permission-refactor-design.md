# 空间化权限模型重构设计

**日期：** 2026-10-17  
**状态：** 设计评审中  
**目标：** 将现有的"家庭共享"权限模型重构为"共享空间+用户空间"的双层隔离模型

---

## 1. 背景与目标

### 1.1 现状问题

当前系统基于 D7 权限模型（`TECH_DECISIONS.md`）：
- 每条数据有 `owner_user_id`（所有者）、`family_id`（家庭）、`visibility`（可见性）
- 写权限：仅所有者
- 读权限：所有者 OR（可见性=family 且同家庭）

**核心问题：**
1. **联系人重复**：同一个人可能被多个用户分别创建，导致数据冗余和不一致
2. **关系隔离不足**：关系（relationships）理应是个人视角的标签（"我的同事"），但当前是家庭共享的
3. **权限粒度单一**：只有"私密"和"家庭共享"两档，缺少"全局共享"的概念
4. **缺少操作审计**：没有记录谁在什么时候修改了什么数据

### 1.2 重构目标

引入**空间（Space）**作为数据归属的抽象层，实现：

1. **联系人去重**：按名字全局去重，一个名字对应唯一一条联系人记录
2. **双层空间模型**：
   - **共享空间（Shared Space）**：家庭级别，所有家庭成员可见可编辑
   - **用户空间（User Space）**：个人级别，仅所有者可见可编辑
3. **关系私有化**：关系完全隔离到用户空间，每人维护自己的人际关系标签
4. **操作可追溯**：所有修改操作记录到审计日志表

### 1.3 核心假设

- **家庭概念保留**：共享空间属于家庭，每个家庭有一个共享空间
- **联系人全局去重**：同一家庭内，一个名字只能有一条联系人记录
- **数据可见性**：用户可以看到所有联系人（共享空间+所有用户空间），但只能编辑自己空间的
- **数据挂载规则**：
  - 联系人、活动、礼物、往来、备注、任务 → 可选择空间
  - 关系 → 强制用户空间

---

## 2. 数据模型设计

### 2.1 新增：spaces 表

```sql
CREATE TABLE spaces (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    type VARCHAR(20) NOT NULL,  -- 'shared' | 'user'
    family_id BIGINT,           -- FK families, 共享空间时必填
    owner_user_id BIGINT,       -- FK users, 用户空间时必填
    name VARCHAR(100) NOT NULL, -- 展示名称
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- 约束：shared 空间必须有 family_id，user 空间必须有 owner_user_id
    CONSTRAINT check_space_type_consistency CHECK (
        (type = 'shared' AND family_id IS NOT NULL AND owner_user_id IS NULL) OR
        (type = 'user' AND owner_user_id IS NOT NULL AND family_id IS NULL)
    ),
    
    -- 约束：每个家庭只有一个共享空间
    CONSTRAINT uq_shared_space_per_family UNIQUE (family_id) WHERE type = 'shared',
    
    -- 约束：每个用户只有一个用户空间
    CONSTRAINT uq_user_space_per_user UNIQUE (owner_user_id) WHERE type = 'user',
    
    FOREIGN KEY (family_id) REFERENCES families(id),
    FOREIGN KEY (owner_user_id) REFERENCES users(id)
);

CREATE INDEX idx_spaces_type ON spaces(type);
CREATE INDEX idx_spaces_family_id ON spaces(family_id);
CREATE INDEX idx_spaces_owner_user_id ON spaces(owner_user_id);
```

**说明：**
- `type='shared'`：共享空间，`family_id` 指向家庭，`owner_user_id` 为 NULL
- `type='user'`：用户空间，`owner_user_id` 指向用户，`family_id` 为 NULL（但可以通过 user 反查到 family）
- `name`：展示名称，如"家庭共享空间"、"张三的个人空间"

### 2.2 修改：contacts 表

```sql
ALTER TABLE contacts
    -- 新增字段
    ADD COLUMN space_id BIGINT NOT NULL,
    ADD COLUMN creator_user_id BIGINT NOT NULL COMMENT '创建者（用于审计和权限判定）',
    
    -- 移除旧字段（由 space 决定归属）
    DROP COLUMN owner_user_id,
    DROP COLUMN visibility,
    
    -- 保留 family_id（冗余字段，用于快速查询和去重约束）
    -- family_id 与 space 的 family_id 保持一致（服务层保证）
    
    -- 新增约束：同一家庭内名字唯一
    ADD CONSTRAINT uq_contact_name_per_family UNIQUE (family_id, name),
    
    -- 外键
    ADD FOREIGN KEY (space_id) REFERENCES spaces(id),
    ADD FOREIGN KEY (creator_user_id) REFERENCES users(id);

CREATE INDEX idx_contacts_space_id ON contacts(space_id);
CREATE INDEX idx_contacts_creator_user_id ON contacts(creator_user_id);
```

**关键变化：**
1. `space_id` 替代 `owner_user_id + visibility`，决定数据归属
2. `creator_user_id` 记录创建者，用于权限判定和审计
3. **名字去重约束**：`UNIQUE (family_id, name)`，同一家庭不能有重名联系人
4. 保留 `family_id` 作为冗余字段，简化查询和约束逻辑

### 2.3 修改：relationships 表

```sql
ALTER TABLE relationships
    -- 新增字段
    ADD COLUMN space_id BIGINT NOT NULL,
    
    -- 保留 owner_user_id（关系的所有者，用于权限判定）
    -- 移除 family_id, visibility（关系强制私有）
    DROP COLUMN family_id,
    DROP COLUMN visibility,
    
    -- 外键
    ADD FOREIGN KEY (space_id) REFERENCES spaces(id),
    
    -- 约束：relationships 只能属于 user 类型的 space
    ADD CONSTRAINT check_relationship_user_space CHECK (
        space_id IN (SELECT id FROM spaces WHERE type = 'user')
    );

CREATE INDEX idx_relationships_space_id ON relationships(space_id);
```

**关键变化：**
1. 关系**强制**属于用户空间（`type='user'`）
2. 保留 `owner_user_id` 作为关系的所有者（与 space.owner_user_id 一致）
3. 移除 `family_id` 和 `visibility`，关系完全私有

### 2.4 修改：其他业务表

**统一改造模式**（activities, gifts, wishlist_items, fund_flows, notes, tasks）：

```sql
-- 以 activities 为例
ALTER TABLE activities
    ADD COLUMN space_id BIGINT NOT NULL,
    ADD COLUMN creator_user_id BIGINT NOT NULL,
    DROP COLUMN visibility,  -- 由 space 决定
    -- 保留 owner_user_id（临时，迁移后可移除）
    
    ADD FOREIGN KEY (space_id) REFERENCES spaces(id),
    ADD FOREIGN KEY (creator_user_id) REFERENCES users(id);
```

**说明：**
- 所有业务表都增加 `space_id` 和 `creator_user_id`
- 移除 `visibility`（由所属 space 的类型决定）
- 保留 `owner_user_id` 和 `family_id`（过渡期保留，迁移完成后可选择移除）

### 2.5 新增：audit_logs 表（操作记录）

```sql
CREATE TABLE audit_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- 操作元数据
    user_id BIGINT NOT NULL COMMENT '操作人',
    action VARCHAR(20) NOT NULL COMMENT '操作类型: create | update | delete | move',
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW() COMMENT '操作时间',
    
    -- 目标对象
    entity_type VARCHAR(50) NOT NULL COMMENT '实体类型: contact | activity | gift | ...',
    entity_id BIGINT NOT NULL COMMENT '实体 ID',
    
    -- 数据快照（JSON）
    old_data JSONB COMMENT '原始数据（update/delete 时记录）',
    new_data JSONB COMMENT '新数据（create/update 时记录）',
    
    -- 上下文信息
    space_id BIGINT COMMENT '操作发生在哪个空间',
    ip_address VARCHAR(50),
    user_agent TEXT,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (space_id) REFERENCES spaces(id)
);

CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_logs_occurred_at ON audit_logs(occurred_at DESC);
CREATE INDEX idx_audit_logs_space_id ON audit_logs(space_id);
```

**字段说明：**
- `action`：操作类型
  - `create`：新建记录
  - `update`：更新记录
  - `delete`：删除记录
  - `move`：移动到另一个空间（如联系人从用户空间移到共享空间）
- `old_data` / `new_data`：JSON 格式存储变更字段
  - `create`：old_data=NULL, new_data=完整记录
  - `update`：old_data=变更前的字段, new_data=变更后的字段
  - `delete`：old_data=完整记录, new_data=NULL
  - `move`：old_data={"space_id": 旧}, new_data={"space_id": 新}

---

## 3. 权限模型重构

### 3.1 核心权限规则

**新权限判定函数**（替代 `app/services/permission.py`）：

```python
from app.modules.auth.models import User
from app.core.models import SpaceMixin  # 新增 Mixin

def get_user_accessible_space_ids(db: AsyncSession, user: User) -> list[int]:
    """获取用户可访问的所有 space ID：
    1. 自己的用户空间
    2. 家庭的共享空间
    3. 同家庭其他成员的用户空间（只读）
    """
    stmt = select(Space.id).where(
        or_(
            # 自己的用户空间
            and_(Space.type == 'user', Space.owner_user_id == user.id),
            # 家庭的共享空间
            and_(Space.type == 'shared', Space.family_id == user.family_id)
        )
    )
    my_spaces = (await db.execute(stmt)).scalars().all()
    
    # 同家庭其他成员的用户空间（只读）
    stmt = select(Space.id).where(
        Space.type == 'user',
        Space.owner_user_id.in_(
            select(User.id).where(User.family_id == user.family_id, User.id != user.id)
        )
    )
    other_user_spaces = (await db.execute(stmt)).scalars().all()
    
    return list(my_spaces) + list(other_user_spaces)

def readable_condition(model_cls: type[SpaceMixin], user: User) -> ColumnElement[bool]:
    """构造"当前用户可读"的 SQL 条件"""
    accessible_space_ids = get_user_accessible_space_ids(db, user)
    return model_cls.space_id.in_(accessible_space_ids)

def can_write(user: User, record: SpaceMixin) -> bool:
    """判断用户是否可写"""
    # 1. 自己用户空间的数据：可写
    if record.space.type == 'user' and record.space.owner_user_id == user.id:
        return True
    
    # 2. 共享空间的数据：可写
    if record.space.type == 'shared' and record.space.family_id == user.family_id:
        return True
    
    # 3. 其他用户空间的数据：不可写
    return False

def ensure_can_write(user: User, record: SpaceMixin) -> None:
    """写权限校验，不通过抛异常"""
    if not can_write(user, record):
        if record.space.type == 'user':
            raise PermissionDeniedError("只能修改自己空间或共享空间的数据")
        else:
            raise PermissionDeniedError("无权修改此空间的数据")
```

### 3.2 特殊规则：关系（Relationships）

关系永远属于用户空间，权限规则：
- **读**：只能看到自己创建的关系
- **写**：只能修改自己创建的关系
- **边的可见性**：关系边的两端联系人可以来自任何可见空间

```python
def get_user_relationships(db: AsyncSession, user: User):
    """查询用户的关系边（只看自己的）"""
    stmt = select(Relationship).where(Relationship.owner_user_id == user.id)
    return (await db.execute(stmt)).scalars().all()
```

### 3.3 权限矩阵

| 数据类型 | 共享空间 | 自己的用户空间 | 他人的用户空间 |
|---------|---------|--------------|--------------|
| 联系人 | 读✓ 写✓ | 读✓ 写✓ | 读✓ 写✗ |
| 活动 | 读✓ 写✓ | 读✓ 写✓ | 读✓ 写✗ |
| 礼物 | 读✓ 写✓ | 读✓ 写✓ | 读✓ 写✗ |
| 往来 | 读✓ 写✓ | 读✓ 写✓ | 读✓ 写✗ |
| 备注 | 读✓ 写✓ | 读✓ 写✓ | 读✓ 写✗ |
| 任务 | 读✓ 写✓ | 读✓ 写✓ | 读✓ 写✗ |
| **关系** | N/A | 读✓ 写✓ | 读✗ 写✗ |

---

## 4. API 变更

### 4.1 新增端点

#### 4.1.1 空间管理

```
GET    /api/v1/spaces              # 获取当前用户可访问的空间列表
GET    /api/v1/spaces/{id}         # 获取空间详情
POST   /api/v1/spaces              # 创建用户空间（注册时自动创建）
PATCH  /api/v1/spaces/{id}         # 更新空间信息（仅 name）
```

**响应示例：**
```json
{
  "spaces": [
    {
      "id": 1,
      "type": "shared",
      "family_id": 1,
      "name": "家庭共享空间",
      "permission": "read_write"
    },
    {
      "id": 2,
      "type": "user",
      "owner_user_id": 10,
      "owner_display_name": "张三",
      "name": "张三的个人空间",
      "permission": "read_write"
    },
    {
      "id": 3,
      "type": "user",
      "owner_user_id": 11,
      "owner_display_name": "李四",
      "name": "李四的个人空间",
      "permission": "read_only"
    }
  ]
}
```

#### 4.1.2 审计日志

```
GET /api/v1/audit-logs?entity_type=contact&entity_id=123
    # 查询某个实体的操作历史

GET /api/v1/audit-logs?user_id=10&start_date=2026-10-01
    # 查询某个用户的操作记录

GET /api/v1/audit-logs?space_id=2&action=update
    # 查询某个空间的修改记录
```

### 4.2 修改现有端点

#### 4.2.1 联系人端点

```
POST /api/v1/contacts
    # 请求体增加 space_id 字段（必填）
    # 默认值：当前用户的 user_space_id

PUT /api/v1/contacts/{id}/move
    # 移动联系人到另一个空间
    # 请求体：{"target_space_id": 1}
    # 规则：只能在 user_space <-> shared_space 之间移动
    # 限制：如果目标空间已有同名联系人，拒绝移动
```

**请求示例：**
```json
POST /api/v1/contacts
{
  "space_id": 2,  // 新增：指定空间，默认用户空间
  "name": "张三",
  "phone": "13800138000",
  ...
}
```

**响应增加字段：**
```json
{
  "id": 123,
  "name": "张三",
  "space_id": 2,
  "space_type": "user",           // 新增
  "space_name": "我的个人空间",    // 新增
  "creator_user_id": 10,          // 新增
  "creator_display_name": "张三",  // 新增
  "can_edit": true,               // 新增：前端据此决定是否显示编辑按钮
  ...
}
```

#### 4.2.2 关系端点

```
GET /api/v1/graph/relationships
    # 只返回当前用户创建的关系
    # 移除 family_id 过滤参数

POST /api/v1/graph/relationships
    # 请求体移除 visibility 字段
    # space_id 自动设为当前用户的 user_space
```

#### 4.2.3 其他业务端点

所有创建/更新端点（activities, gifts, funds, notes, tasks）：
- 请求体增加 `space_id` 字段（必填，默认用户空间）
- 响应增加 `space_type`, `space_name`, `can_edit` 字段

---

## 5. 数据迁移方案

### 5.1 迁移步骤

**Phase 1: 创建 spaces 表并初始化**

```sql
-- 1. 创建 spaces 表
CREATE TABLE spaces (...);  -- 见 2.1 节

-- 2. 为每个家庭创建一个共享空间
INSERT INTO spaces (type, family_id, name, created_at, updated_at)
SELECT 
    'shared' AS type,
    id AS family_id,
    CONCAT(name, ' - 共享空间') AS name,
    NOW() AS created_at,
    NOW() AS updated_at
FROM families;

-- 3. 为每个用户创建一个用户空间
INSERT INTO spaces (type, owner_user_id, name, created_at, updated_at)
SELECT 
    'user' AS type,
    id AS owner_user_id,
    CONCAT(display_name, ' 的个人空间') AS name,
    NOW() AS created_at,
    NOW() AS updated_at
FROM users
WHERE is_active = TRUE;
```

**Phase 2: 迁移联系人数据**

```sql
-- 1. 添加新字段（允许 NULL，迁移后改为 NOT NULL）
ALTER TABLE contacts
    ADD COLUMN space_id BIGINT,
    ADD COLUMN creator_user_id BIGINT;

-- 2. 迁移数据
-- 2.1 visibility='family' → 共享空间
UPDATE contacts c
SET 
    space_id = s.id,
    creator_user_id = c.owner_user_id
FROM spaces s
WHERE 
    c.visibility = 'family'
    AND s.type = 'shared'
    AND s.family_id = c.family_id;

-- 2.2 visibility='private' → 用户空间
UPDATE contacts c
SET 
    space_id = s.id,
    creator_user_id = c.owner_user_id
FROM spaces s
WHERE 
    c.visibility = 'private'
    AND s.type = 'user'
    AND s.owner_user_id = c.owner_user_id;

-- 3. 处理名字重复问题（手动干预）
-- 查询重复的联系人
SELECT 
    family_id, 
    name, 
    COUNT(*) as cnt,
    STRING_AGG(CAST(id AS VARCHAR), ', ') as ids
FROM contacts
GROUP BY family_id, name
HAVING COUNT(*) > 1;

-- 对于重复的联系人，需要手动决策：
-- a) 合并为一条记录（推荐）：选择一条保留，其他记录的关联数据迁移到保留记录
-- b) 重命名：给其中一个联系人的 name 加后缀，如 "张三(2)"

-- 4. 添加唯一约束
ALTER TABLE contacts
    ADD CONSTRAINT uq_contact_name_per_family UNIQUE (family_id, name);

-- 5. 设置字段为 NOT NULL
ALTER TABLE contacts
    ALTER COLUMN space_id SET NOT NULL,
    ALTER COLUMN creator_user_id SET NOT NULL;

-- 6. 添加外键
ALTER TABLE contacts
    ADD FOREIGN KEY (space_id) REFERENCES spaces(id),
    ADD FOREIGN KEY (creator_user_id) REFERENCES users(id);

-- 7. 删除旧字段（可选，建议保留一段时间以便回滚）
-- ALTER TABLE contacts DROP COLUMN owner_user_id;
-- ALTER TABLE contacts DROP COLUMN visibility;
```

**Phase 3: 迁移关系数据**

```sql
-- 1. 添加新字段
ALTER TABLE relationships ADD COLUMN space_id BIGINT;

-- 2. 迁移数据：所有关系迁移到创建者的用户空间
UPDATE relationships r
SET space_id = s.id
FROM spaces s
WHERE 
    s.type = 'user'
    AND s.owner_user_id = r.owner_user_id;

-- 3. 设置 NOT NULL 并添加约束
ALTER TABLE relationships
    ALTER COLUMN space_id SET NOT NULL,
    ADD FOREIGN KEY (space_id) REFERENCES spaces(id);

-- 4. 删除旧字段
ALTER TABLE relationships
    DROP COLUMN family_id,
    DROP COLUMN visibility;
```

**Phase 4: 迁移其他业务表**

类似 contacts 的迁移逻辑，按表依次执行：
- activities
- gifts / wishlist_items
- fund_flows
- notes
- tasks

```sql
-- 以 activities 为例
ALTER TABLE activities
    ADD COLUMN space_id BIGINT,
    ADD COLUMN creator_user_id BIGINT;

UPDATE activities a
SET 
    space_id = CASE 
        WHEN a.visibility = 'family' THEN (SELECT id FROM spaces WHERE type='shared' AND family_id=a.family_id)
        ELSE (SELECT id FROM spaces WHERE type='user' AND owner_user_id=a.owner_user_id)
    END,
    creator_user_id = a.owner_user_id;

ALTER TABLE activities
    ALTER COLUMN space_id SET NOT NULL,
    ALTER COLUMN creator_user_id SET NOT NULL,
    ADD FOREIGN KEY (space_id) REFERENCES spaces(id),
    ADD FOREIGN KEY (creator_user_id) REFERENCES users(id),
    DROP COLUMN visibility;
```

### 5.2 回滚方案

```sql
-- 如果迁移失败，可以回滚：
-- 1. 从 space_id 反推 visibility
UPDATE contacts
SET visibility = CASE
    WHEN s.type = 'shared' THEN 'family'
    ELSE 'private'
END
FROM spaces s
WHERE contacts.space_id = s.id;

-- 2. 删除新字段
ALTER TABLE contacts
    DROP COLUMN space_id,
    DROP COLUMN creator_user_id,
    DROP CONSTRAINT uq_contact_name_per_family;

-- 3. 删除 spaces 表
DROP TABLE spaces;
```

### 5.3 迁移风险与缓解

**风险1：联系人名字重复**
- **影响**：无法添加唯一约束，迁移中断
- **缓解**：
  1. 迁移前先运行重复检测查询，导出清单
  2. 与用户沟通，手动合并或重命名重复联系人
  3. 提供合并工具：自动迁移关联数据（关系、活动等）到保留的联系人

**风险2：数据量大，迁移时间长**
- **影响**：迁移期间服务不可用
- **缓解**：
  1. 在低峰期执行
  2. 分批迁移（先小表后大表）
  3. 使用事务，失败自动回滚

**风险3：前端不兼容**
- **影响**：后端迁移完成但前端未更新，接口不匹配
- **缓解**：
  1. 后端保持向后兼容（临时支持旧字段）
  2. 灰度发布：先部署后端，观察无误后部署前端
  3. API 版本化：`/api/v2/contacts` 使用新模型，旧版本保留一段时间

---

## 6. 操作记录（Audit Log）实现

### 6.1 记录时机

**自动记录点**（在 service 层统一拦截）：
- `create_*` 函数：记录 `action=create`
- `update_*` 函数：记录 `action=update`
- `delete_*` 或 `archive_*` 函数：记录 `action=delete`
- `move_to_space` 函数：记录 `action=move`

### 6.2 实现方式

**Option A：装饰器模式**（推荐）

```python
# app/services/audit.py
from functools import wraps
import inspect

def audit_log(entity_type: str):
    """装饰器：自动记录操作日志"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 解析参数
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            db = bound.arguments.get('db')
            user = bound.arguments.get('user')
            
            # 执行原函数
            result = await func(*args, **kwargs)
            
            # 判断操作类型
            if 'create' in func.__name__:
                action = 'create'
                old_data = None
                new_data = result.model_dump(mode='json')  # Pydantic 输出
            elif 'update' in func.__name__:
                action = 'update'
                # 从参数中提取原始记录和变更数据
                # ...
            elif 'delete' in func.__name__ or 'archive' in func.__name__:
                action = 'delete'
                # ...
            
            # 写入审计日志
            await create_audit_log(
                db=db,
                user_id=user.id,
                action=action,
                entity_type=entity_type,
                entity_id=result.id,
                old_data=old_data,
                new_data=new_data,
                space_id=result.space_id
            )
            
            return result
        return wrapper
    return decorator

# 使用示例
@audit_log(entity_type='contact')
async def create_contact(db: AsyncSession, user: User, data: ContactCreate):
    # ... 创建逻辑
    return contact
```

**Option B：手动调用**

```python
# 在每个 service 函数中手动调用
async def update_contact(db: AsyncSession, user: User, contact_id: int, data: ContactUpdate):
    # 1. 加载原始记录
    old_contact = await get_contact(db, contact_id)
    old_data = old_contact.model_dump(mode='json')
    
    # 2. 执行更新
    updated_contact = await _do_update(db, old_contact, data)
    new_data = updated_contact.model_dump(mode='json')
    
    # 3. 记录审计日志
    await create_audit_log(
        db=db,
        user_id=user.id,
        action='update',
        entity_type='contact',
        entity_id=contact_id,
        old_data=extract_changed_fields(old_data, new_data),  # 只记录变更字段
        new_data=extract_changed_fields(old_data, new_data, inverse=True),
        space_id=updated_contact.space_id
    )
    
    return updated_contact
```

### 6.3 数据结构示例

**创建联系人：**
```json
{
  "action": "create",
  "entity_type": "contact",
  "entity_id": 123,
  "old_data": null,
  "new_data": {
    "name": "张三",
    "phone": "13800138000",
    "space_id": 2
  }
}
```

**更新联系人：**
```json
{
  "action": "update",
  "entity_type": "contact",
  "entity_id": 123,
  "old_data": {
    "phone": "13800138000",
    "email": null
  },
  "new_data": {
    "phone": "13900139000",
    "email": "zhangsan@example.com"
  }
}
```

**移动联系人到共享空间：**
```json
{
  "action": "move",
  "entity_type": "contact",
  "entity_id": 123,
  "old_data": {
    "space_id": 2,
    "space_type": "user"
  },
  "new_data": {
    "space_id": 1,
    "space_type": "shared"
  }
}
```

### 6.4 审计日志查询 API

```python
# app/modules/audit/api.py
@router.get("/audit-logs", response_model=list[AuditLogOut])
async def list_audit_logs(
    entity_type: str | None = None,
    entity_id: int | None = None,
    user_id: int | None = None,
    space_id: int | None = None,
    action: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询审计日志（支持多维度过滤）"""
    # 权限检查：只能查询自己可见空间的日志
    accessible_space_ids = await get_user_accessible_space_ids(db, current_user)
    
    stmt = select(AuditLog).where(AuditLog.space_id.in_(accessible_space_ids))
    
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    # ... 其他过滤条件
    
    stmt = stmt.order_by(AuditLog.occurred_at.desc()).limit(limit).offset(offset)
    
    result = await db.execute(stmt)
    return result.scalars().all()
```

---

## 7. 前端适配

### 7.1 UI 变更

**1. 联系人列表页**
- 增加"空间"筛选器：全部 / 共享空间 / 我的空间 / 其他用户空间
- 列表项增加空间标识图标：
  - 共享空间：🌐
  - 自己的空间：🔒
  - 他人的空间：👤（灰色，只读）
- 编辑按钮根据 `can_edit` 字段控制是否显示

**2. 联系人创建/编辑表单**
- 增加"所属空间"选择器（下拉框）：
  - 默认值：我的个人空间
  - 可选项：我的个人空间、家庭共享空间
- 移动按钮（仅详情页）：
  - 条件：当前在用户空间 且 共享空间无同名联系人
  - 操作：调用 `PUT /contacts/{id}/move` API

**3. 关系管理页**
- 移除"可见性"选项（强制私有）
- 标注"这是您的个人关系标签，仅您可见"

**4. 其他数据创建表单**
- 增加"保存到"选择器：我的空间 / 共享空间
- 默认值：继承关联联系人的空间（如果有）

**5. 新增：操作记录查看**
- 联系人详情页增加"操作历史"Tab
- 显示时间线：谁 在 何时 做了 什么操作
- 支持展开查看详细变更（old_data vs new_data 的 diff）

### 7.2 API 调用调整

```typescript
// api/spaces.ts
export interface Space {
  id: number;
  type: 'shared' | 'user';
  name: string;
  permission: 'read_write' | 'read_only';
  owner_display_name?: string;
}

export async function getSpaces(): Promise<Space[]> {
  const res = await http.get('/api/v1/spaces');
  return res.data.spaces;
}

// api/contacts.ts
export interface ContactCreate {
  space_id: number;  // 新增：必填
  name: string;
  // ... 其他字段
}

export interface ContactOut {
  id: number;
  space_id: number;
  space_type: 'shared' | 'user';  // 新增
  space_name: string;              // 新增
  can_edit: boolean;               // 新增
  // ... 其他字段
}

export async function moveContactToSpace(
  contactId: number, 
  targetSpaceId: number
): Promise<void> {
  await http.put(`/api/v1/contacts/${contactId}/move`, {
    target_space_id: targetSpaceId
  });
}

// api/audit.ts
export interface AuditLog {
  id: number;
  user_id: number;
  user_display_name: string;
  action: 'create' | 'update' | 'delete' | 'move';
  entity_type: string;
  entity_id: number;
  old_data: Record<string, any> | null;
  new_data: Record<string, any> | null;
  occurred_at: string;
}

export async function getEntityAuditLogs(
  entityType: string,
  entityId: number
): Promise<AuditLog[]> {
  const res = await http.get('/api/v1/audit-logs', {
    params: { entity_type: entityType, entity_id: entityId }
  });
  return res.data;
}
```

---

## 8. 测试计划

### 8.1 单元测试

**权限判定测试**（`tests/services/test_permission_v2.py`）：
```python
async def test_user_can_read_shared_space_data():
    # 用户 A 能读取共享空间的联系人
    assert await can_read(user_a, contact_in_shared_space) == True

async def test_user_cannot_write_other_user_space_data():
    # 用户 A 不能修改用户 B 空间的联系人
    assert await can_write(user_a, contact_in_user_b_space) == False

async def test_relationship_only_visible_to_owner():
    # 关系只对创建者可见
    relationships = await get_user_relationships(db, user_a)
    assert all(r.owner_user_id == user_a.id for r in relationships)
```

**名字去重测试**（`tests/modules/contacts/test_deduplication.py`）：
```python
async def test_cannot_create_duplicate_name_in_same_family():
    # 同一家庭不能创建同名联系人
    await create_contact(db, user_a, ContactCreate(name="张三", ...))
    with pytest.raises(IntegrityError):
        await create_contact(db, user_a, ContactCreate(name="张三", ...))

async def test_cannot_move_contact_if_name_exists_in_target_space():
    # 目标空间有同名联系人时，移动失败
    await create_contact(db, user_a, ContactCreate(name="张三", space_id=shared_space.id))
    contact_b = await create_contact(db, user_b, ContactCreate(name="张三", space_id=user_b_space.id))
    
    with pytest.raises(ValidationError):
        await move_contact_to_space(db, user_b, contact_b.id, shared_space.id)
```

**审计日志测试**（`tests/services/test_audit.py`）：
```python
async def test_audit_log_created_on_contact_update():
    # 更新联系人时自动创建审计日志
    contact = await create_contact(db, user, ...)
    await update_contact(db, user, contact.id, ContactUpdate(phone="13900139000"))
    
    logs = await get_audit_logs(db, entity_type='contact', entity_id=contact.id)
    assert len(logs) == 2  # 1 create + 1 update
    assert logs[1].action == 'update'
    assert logs[1].old_data['phone'] == "13800138000"
    assert logs[1].new_data['phone'] == "13900139000"
```

### 8.2 集成测试

**端到端场景测试**（`tests/integration/test_space_workflow.py`）：
```python
async def test_contact_creation_and_sharing_workflow():
    """完整流程：创建联系人 → 移动到共享空间 → 其他用户查看和编辑"""
    # 1. 用户 A 创建联系人到自己空间
    contact = await create_contact(db, user_a, ContactCreate(
        name="张三",
        space_id=user_a_space.id,
        phone="13800138000"
    ))
    
    # 2. 用户 B 此时看不到（在 A 的私人空间）
    contacts_for_b = await list_contacts(db, user_b)
    assert contact.id not in [c.id for c in contacts_for_b]
    
    # 3. 用户 A 移动到共享空间
    await move_contact_to_space(db, user_a, contact.id, shared_space.id)
    
    # 4. 用户 B 现在可以看到并编辑
    contacts_for_b = await list_contacts(db, user_b)
    assert contact.id in [c.id for c in contacts_for_b]
    
    updated = await update_contact(db, user_b, contact.id, ContactUpdate(
        email="zhangsan@example.com"
    ))
    assert updated.email == "zhangsan@example.com"
    
    # 5. 审计日志记录了 A 的创建、A 的移动、B 的更新
    logs = await get_audit_logs(db, entity_id=contact.id)
    assert len(logs) == 3
    assert logs[0].action == 'create' and logs[0].user_id == user_a.id
    assert logs[1].action == 'move' and logs[1].user_id == user_a.id
    assert logs[2].action == 'update' and logs[2].user_id == user_b.id
```

### 8.3 性能测试

**查询性能测试**：
- 测试场景：1个家庭、10个用户、每个用户1000个联系人
- 指标：
  - `GET /contacts` 响应时间 < 200ms
  - `GET /contacts/{id}` 响应时间 < 50ms
  - `GET /audit-logs?entity_id=123` 响应时间 < 100ms

**迁移性能测试**：
- 测试场景：100万条联系人记录
- 指标：
  - 迁移脚本执行时间 < 30分钟
  - 数据一致性校验通过率 100%

---

## 9. 实施计划

### 9.1 时间线（预估）

| 阶段 | 任务 | 工作量 | 依赖 |
|-----|------|--------|------|
| **Week 1** | 数据库迁移脚本编写与测试 | 3天 | - |
| | 后端 Models & Mixins 重构 | 2天 | - |
| **Week 2** | 权限模块重构（permission.py） | 2天 | Models |
| | Service 层适配（contacts, relationships, ...） | 3天 | 权限模块 |
| **Week 3** | API 端点更新（spaces, audit-logs） | 2天 | Service 层 |
| | 审计日志实现（装饰器 + 查询接口） | 2天 | API 端点 |
| | 单元测试与集成测试 | 1天 | 所有后端 |
| **Week 4** | 前端 API 客户端更新 | 1天 | API 端点 |
| | 前端 UI 组件适配（空间选择器、操作历史） | 3天 | API 客户端 |
| | 前端测试与联调 | 1天 | 所有前端 |
| **Week 5** | 数据迁移执行（生产环境） | 1天 | 所有开发 |
| | 监控与修复 | 2天 | 迁移执行 |
| | 文档更新 | 1天 | - |

**总计：约 5 周**

### 9.2 风险缓解措施

1. **数据迁移风险**：
   - 在测试环境完整预演迁移流程
   - 迁移前完整备份数据库
   - 准备回滚脚本（已在 5.2 节提供）

2. **性能风险**：
   - 在迁移前对关键查询添加索引
   - 使用 EXPLAIN ANALYZE 验证查询计划
   - 分批迁移大表，避免长事务锁表

3. **兼容性风险**：
   - 后端保持 1 个月的向后兼容期（支持旧 API 参数）
   - 灰度发布：先 10% 用户，观察无误后全量
   - 提供紧急回滚开关（功能开关）

---

## 10. 未来扩展

### 10.1 可能的增强方向

1. **更细粒度的权限**：
   - 字段级权限：共享空间的联系人，某些字段（如"银行卡号"）仅创建者可见
   - 操作级权限：共享空间允许"只读"成员（不能修改但能查看）

2. **协作空间**：
   - 引入 `type='project'` 的项目空间
   - 支持邀请特定用户协作（跨家庭共享）

3. **审计日志增强**：
   - 支持撤销操作（Undo）：基于 audit_log 回滚最近一次修改
   - 审计日志导出（CSV/JSON）

4. **空间模板**：
   - 创建用户时，可以选择空间模板（如"商务人脉"、"家庭关系"）
   - 模板预置关系类型、标签等

### 10.2 技术债务

1. **旧字段清理**：
   - 迁移后 1 个月，确认稳定后删除 `owner_user_id`, `visibility` 列
   - 更新所有迁移脚本的 `down` 逻辑

2. **代码重复**：
   - 各业务表的迁移逻辑高度相似，可以提取通用迁移函数
   - Service 层的审计日志记录代码可以进一步抽象

---

## 11. 总结

### 11.1 核心价值

1. **数据去重**：联系人按名字唯一，避免冗余和不一致
2. **灵活共享**：双层空间模型满足"全局共享"和"个人私密"两种需求
3. **关系私有化**：关系作为个人视角的标签，完全隔离
4. **操作可追溯**：审计日志记录所有变更，满足合规和排查需求

### 11.2 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 空间模型 | 新增 `spaces` 表 | 清晰的抽象层，易扩展 |
| 去重范围 | 家庭级别 | 符合现有"家庭"概念，避免跨家庭冲突 |
| 关系归属 | 强制用户空间 | 关系是个人视角，不应共享 |
| 审计实现 | 装饰器模式 | 自动化记录，减少遗漏 |
| 数据迁移 | 分阶段执行 | 降低风险，可灰度回滚 |

### 11.3 注意事项

1. **名字去重的用户教育**：
   - 迁移前需要通知用户：同名联系人将被合并或重命名
   - 提供合并工具和预览界面，让用户确认合并结果

2. **权限模型的沟通**：
   - 用户可能不理解"看到他人空间但不能编辑"的逻辑
   - 需要在 UI 上清晰标识（图标、颜色、禁用按钮）

3. **审计日志的存储成本**：
   - 高频操作会产生大量日志，需要定期归档
   - 建议：超过 1 年的日志迁移到冷存储（如 S3）

---

**本规格文档完成。下一步：等待用户评审，确认无误后进入实施计划编写阶段。**
