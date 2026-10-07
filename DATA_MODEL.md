# 数据模型设计（Level 1 基准，随 Level 迭代扩展）

> 依据：`TECH_DECISIONS.md` D3（PostgreSQL + pgvector）、D6（AI）、D7（权限）、D11（MCP）。
> 所有业务表统一遵守 D7：所有者写入隔离 + 可见性两档（private 私密 / family 家庭可见只读）。
> 命名：表名复数蛇形；主键 `id` BIGINT 自增；外键显式命名；时间戳一律 timestamptz。

## 1. 账号与家庭

### families 家庭组
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| name | VARCHAR(100) | 家庭名称，如"我们家" |
| created_at / updated_at | TIMESTAMPTZ | |

### users 用户
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| family_id | BIGINT FK→families | 一个用户只属一个家庭组（D7：不做多层组织） |
| username | VARCHAR(50) UNIQUE | 登录名，小写存储 |
| display_name | VARCHAR(50) | 展示名（如"老公""老婆"） |
| password_hash | VARCHAR(255) | pwdlib bcrypt |
| is_active | BOOLEAN | 停用开关 |
| created_at / updated_at | TIMESTAMPTZ | |

### user_tokens 外部客户端访问令牌（D11，MCP 用）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| user_id | BIGINT FK→users | 令牌以该用户身份操作 |
| name | VARCHAR(100) | 令牌用途备注，如"Claude Desktop" |
| token_hash | VARCHAR(255) | 仅存哈希 |
| scopes | JSONB | 预留：["read","write"] |
| last_used_at / revoked_at | TIMESTAMPTZ NULL | |
| created_at | TIMESTAMPTZ | |

### app_settings 运行时配置（D6.2：LLM 等页面可改）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| key | VARCHAR(100) UNIQUE | 如 `ai.llm` |
| value | JSONB | 结构化配置（provider/base_url/api_key/model） |
| updated_by | BIGINT FK→users NULL | |
| updated_at | TIMESTAMPTZ | |

## 2. 联系人（双层模型）

### contacts 联系人
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| owner_user_id | BIGINT FK→users | 所有者，唯一可写（D7） |
| family_id | BIGINT FK→families | 冗余家庭 ID，服务层保证与 owner 一致，用于家庭范围查询 |
| tier | ENUM(direct, edge) | 直接联系人 / 边缘联系人（叶子）；升级 = 改 tier，数据无损 |
| name | VARCHAR(100) NOT NULL DEFAULT '' | 姓名（中文姓名整体存储，D23；不再拆分姓/名） |
| nickname | VARCHAR(100) NULL | 昵称/称呼（外号、亲近称呼，如"老王""三婶"） |
| gender | ENUM(male, female, other, unknown) | |
| organization | VARCHAR(100) NULL | 公司/单位 |
| phone | VARCHAR(30) NULL | 电话 |
| qq | VARCHAR(30) NULL | QQ 号 |
| wechat | VARCHAR(50) NULL | 微信号 |
| email | VARCHAR(120) NULL | 邮箱 |
| current_address | VARCHAR(200) NULL | 现居地（详细地址） |
| family_address | VARCHAR(200) NULL | 家庭地址（老家） |
| hobbies | VARCHAR(300) NULL | 兴趣爱好（自由文本） |
| school_name | VARCHAR(100) NULL | 毕业院校（文本 + distinct 列表做选择/筛选，支持校友查找） |
| location | VARCHAR(200) NULL | 所在地文本（"上海市浦东新区"，城市级，地图用），保存时经 geo 模块解析坐标（D14） |
| location_lng | DOUBLE PRECISION NULL | 经度缓存（geo 解析结果，location 变更才重算） |
| location_lat | DOUBLE PRECISION NULL | 纬度缓存（同上） |
| location_source | VARCHAR(10) NULL | 坐标来源：amap / static / none（NULL=未解析） |
| bio | TEXT NULL | 一句话简介 |
| avatar_path | VARCHAR(255) NULL | 本地卷相对路径（D10 首版本地存储） |
| visibility | ENUM(private, family) | D7 可见性 |
| status | ENUM(active, archived) | 归档代替删除，保护历史关系边 |
| created_at / updated_at | TIMESTAMPTZ | |

索引：`(family_id, status)`、`(owner_user_id)`；同名检测按姓名全等查询，当前数据量走上述索引即可，不单建。`search_text` 生成列 + pg_trgm GIN 曾列入 Level 1 计划但从未实现（名册搜索走 `name`/`nickname` 的 ILIKE），需要全文检索时再补。

**展示名规则**（model property 唯一实现，禁在前端重复实现）：`nickname > name > 「（未命名）」`。

## 3. 关系（图）

### relationship_types 关系类型字典
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| group_name | ENUM(family, friend, work, romance, other) | 分组 |
| name | VARCHAR(50) | 正向标签，如"丈夫" |
| reverse_name | VARCHAR(50) NULL | 反向标签，如"妻子"；NULL=对称关系（同事） |
| is_system | BOOLEAN | 系统结构化类型（D15）：可参与称谓推导；自定义类型 false |
| kind | VARCHAR(20) NULL | 系统类型的结构类别：parent / spouse / sibling；自定义 NULL |
| sort_order | SMALLINT | 展示排序 |

种子数据随迁移写入（夫妻/父母/子女/兄弟姐妹/同事/朋友/同学/邻居等 ~30 条，可扩展）。
**系统类型三条**（D15，role 值域由代码常量定义）：parent（父母-子女）、spouse（配偶）、sibling（兄弟姐妹，按长幼）。

### relationships 关系边
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| from_contact_id | BIGINT FK→contacts | 主体（"A 是 B 的丈夫"：from=A） |
| to_contact_id | BIGINT FK→contacts | 客体 |
| type_id | BIGINT FK→relationship_types | |
| from_role | VARCHAR(30) NULL | from 是 to 的角色（father/husband/elder_brother…），系统类型必填 |
| to_role | VARCHAR(30) NULL | to 是 from 的角色（son/wife/younger_brother…） |
| status | VARCHAR(10) | active / former（离异、断绝等历史关系保留）；默认 active |
| owner_user_id | BIGINT FK→users | 谁建谁维护；跨用户边允许（D7 细化） |
| note | VARCHAR(200) NULL | 补充说明 |
| created_at / updated_at | TIMESTAMPTZ | |

唯一约束 `(from_contact_id, to_contact_id, type_id)`。
**可见性不落库**：边的可见性 = 两端联系人可见性取交集（查询期计算，D7 细化决策）。
edge↔edge 边：数据层允许（建边时两端须为 active 且对创建者可读），UI 不提供入口。
**视角解析（D15）**：查询时按当前节点在边的哪一端取对端 role 字段；role 为空（旧数据/自定义类型）退回 name/reverse_name 句式。
**"我"的绑定（D15）**：users.contact_id（可空 FK→contacts，唯一）把账号锚定到联系人节点，称谓推导以它为起点。

## 4. 时间与生活记录（表结构定稿 2026-09-21，功能 Level 3 落地）

### important_dates 重要日期（D8 农历原生支持）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| contact_id | BIGINT FK→contacts | |
| owner_user_id / family_id / visibility | 同 D7 三件套 | |
| type | ENUM(birthday, anniversary, memorial, other) | |
| title | VARCHAR(100) NULL | 自定义名（"结婚纪念日"） |
| calendar | ENUM(solar, lunar) | 历法 |
| date_solar | DATE NULL | calendar=solar 时必填 |
| lunar_month / lunar_day | SMALLINT NULL | calendar=lunar 时必填（1-12 / 1-30） |
| lunar_is_leap | BOOLEAN | 闰月标志 |
| yearly | BOOLEAN | 是否每年重复 |
| reminder_lead_days | JSONB | 提前提醒天数列表，如 `[7,1]` |
| created_at / updated_at | TIMESTAMPTZ | |

### notes 备注 / tasks 待办
统一骨架：`id + owner_user_id + family_id + visibility + created_at/updated_at`（SQLAlchemy `OwnershipMixin` 一处实现），差异字段：
- notes: `contact_id nullable FK` + `content TEXT`
- tasks: `contact_id nullable` + `title VARCHAR(200)` + `detail TEXT nullable` + `due_at TIMESTAMPTZ nullable` + `status ENUM(todo, done, cancelled)` + `completed_at`

### activities 活动 + activity_participants 参与者（2026-09-21 用户定稿：一次活动对多名参与者）
activities 本体不再直接挂 contact_id，经参与者表关联：

| 字段 | 类型 | 说明 |
|---|---|---|
| id + D7 三件套 + 时间戳 | | |
| title | VARCHAR(200) | 活动标题 |
| occurred_at | TIMESTAMPTZ | 活动时间 |
| location | VARCHAR(200) NULL | 地点 |
| detail | TEXT NULL | 记录详情（Markdown） |

| activity_participants | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| activity_id | BIGINT FK→activities | 活动删除级联删参与者 |
| contact_id | BIGINT FK→contacts | 参与者 |

唯一约束 `(activity_id, contact_id)`。参与者行的读权限**跟随活动本身**（D7，不单独判权）；联系人详情页展示"参与的活动"，活动管理页展示参与者名单（对查看者不可读的参与者只计数字不出名字）。

### gifts 礼物往来（已送出 / 已收到）
| 字段 | 类型 | 说明 |
|---|---|---|
| id + D7 三件套 + 时间戳 | | |
| contact_id | BIGINT FK→contacts NULL | 对象联系人（家庭层面往来可空，UI 引导必选） |
| direction | ENUM(given, received) | 送出 / 收到 |
| title | VARCHAR(200) | 礼物名称 |
| occasion | VARCHAR(100) NULL | 场合（生日/婚礼/探病…自由文本） |
| amount | NUMERIC(12,2) NULL | 金额（可选） |
| currency | VARCHAR(8) DEFAULT 'CNY' | 币种 |
| given_at | DATE NULL | 送出/收到日期 |
| link | VARCHAR(500) NULL | 购买/参考链接（可选） |
| description | TEXT NULL | 礼物说明（Markdown 可编辑） |

### wishlist_items 愿望清单（还没送出）
| 字段 | 类型 | 说明 |
|---|---|---|
| id + D7 三件套 + 时间戳 | | |
| contact_id | BIGINT FK→contacts NULL | 为谁准备 |
| title | VARCHAR(200) | 想送的礼物 |
| amount | NUMERIC(12,2) NULL | 预算/价格（可选） |
| currency | VARCHAR(8) DEFAULT 'CNY' | 币种 |
| link | VARCHAR(500) NULL | 购买链接（可选） |
| description | TEXT NULL | 说明（Markdown 可编辑） |
| status | ENUM(open, purchased, given) | 想送 / 已购买 / 已送出 |
| target_date | DATE NULL | 打算送出的日期（如对方生日） |
| converted_gift_id | BIGINT FK→gifts NULL | 送出后转为礼物记录的回链 |

### fund_flows 资金往来（借贷等）
| 字段 | 类型 | 说明 |
|---|---|---|
| id + D7 三件套 + 时间戳 | | |
| contact_id | BIGINT FK→contacts NULL | 对象联系人 |
| direction | ENUM(out, in) | 流出（借出/支出） / 流入（借入/收到） |
| category | ENUM(loan, repayment, gift_money, other) | 借款 / 还款 / 礼金 / 其他 |
| amount | NUMERIC(12,2) NOT NULL | 金额 |
| currency | VARCHAR(8) DEFAULT 'CNY' | 币种 |
| occurred_at | DATE NOT NULL | 发生日 |
| due_at | DATE NULL | 应收/应还日——**主页"还款提醒"待办的数据源** |
| status | ENUM(pending, settled) | 未结清 / 已结清 |
| settled_at | DATE NULL | 结清日 |
| description | TEXT NULL | 说明（Markdown 可编辑） |

> gifts / wishlist_items / fund_flows 各带**独立管理页面**（列表 + 搜索 + CRUD，2026-09-21 用户要求），并聚合进联系人详情页；主页统计后续增量消费（未结清借款、年度送礼支出等），dashboard 的待办分类与统计块均按可扩展结构设计。

## 5. AI 与集成（Level 4 落地，Level 1 建基础设施表）

### pending_actions MCP 写入确认队列（D11）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| family_id / requested_by_user_id | FK | 提议人 |
| tool_name | VARCHAR(100) | MCP 工具名 |
| payload | JSONB | 工具入参 |
| preview | JSONB NULL | 确认面板的渲染快照（update 放改动字段原值、delete 放实体摘要）；与 payload 分离，执行器只读 payload |
| reason | TEXT NULL | agent 的提议理由（展示给确认人） |
| status | ENUM(pending, approved, rejected, expired, executed) | 状态机 |
| decided_by | BIGINT FK→users NULL | 确认人 |
| result | JSONB NULL | 执行结果摘要 |
| created_at / decided_at / executed_at | TIMESTAMPTZ | |

### embeddings 语义向量（✅ 已建表 2026-09-21，维度定稿见 D6.3 细化）
| 字段 | 类型 | 说明 |
|---|---|---|
| id + owner_user_id / family_id / visibility | D7 三件套 | 可见性快照自源数据 |
| entity_type | ENUM(contact, activity, gift, fund, note) | 业务实体类型 |
| entity_id | BIGINT | 业务数据 id（**元数据关联，无硬 FK**，删除由对账清理） |
| content | TEXT | 被向量化的文本快照 |
| content_hash | VARCHAR(64) | 源内容哈希（变更时按需重新生成） |
| model | VARCHAR(100) | 生成模型（换模型全量重建） |
| embedding | VECTOR(1024) | 维度固定 1024（换供应商不换维度） |

唯一约束 `(entity_type, entity_id)`；对账管线见 `app/modules/ai/semantic.py`。

## 6. 权限判定（唯一实现点）

`app/services/permission.py` 提供：
- `readable_filter(user, Model)` — 读取范围 SQL 条件：`(owner==me) OR (visibility=family AND family_id==my_family)`
- `ensure_can_write(user, record)` — 非所有者写操作抛 `PermissionDeniedError`（API 层转 403）

REST API、MCP 工具、内部 agent 一律经过它，**禁止其他路径判权**（D11 红线）。

## activity_images（活动图片，D18）

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK, autoincrement | |
| activity_id | BIGINT | FK activities(id) **ON DELETE CASCADE**, index | 所属活动；图片行随活动删除 |
| path | VARCHAR(500) | NOT NULL | 正式区相对路径，如 `activities/2026/09/<uuid>.jpg` |
| thumb_path | VARCHAR(500) | NOT NULL | 缩略图相对路径（长边 400px） |
| sort_order | INTEGER | NOT NULL, index | 展示顺序，升序；**最小者为时间线封面** |
| created_at / updated_at | TIMESTAMPTZ | server_default now() | TimestampMixin |

不带 D7 三件套：可见性完全跟随所属活动（同 `activity_participants` 的取舍）。
**文件删除**不在级联里——由 records service 在事务提交后经 `storage.defer_delete` 执行。
