# 技术选型与架构决策记录

> 文档目的：集中记录 personal-crm 的全部技术决策、备选方案与决策理由，避免后续会话对已定事项重新翻案。随讨论推进持续更新。
>
> 需求背景见 `PROJECT_BACKGROUND.md`，工程规范见 `AGENTS.md`。
>
> 状态标记：✅ 已决策 ｜ 🔄 有明确倾向待确认 ｜ ⬜ 待讨论

---

## 决策总览

| # | 决策 | 状态 | 决策日期 |
|---|---|---|---|
| D1 | 整体形态：全新自研，不 fork Monica | ✅ | 2026-09-20 |
| D2 | 架构形态：FastAPI + Vue 3 前后端分离，单仓库，一体化部署 | ✅ | 2026-09-20 |
| D3 | 数据库：PostgreSQL + pgvector 单库；关系图用邻接表 + 递归 CTE | ✅ | 2026-09-20 |
| D4 | 前端组件库：~~Naive UI~~ → **Element Plus**（2026-09-22 用户指令，并入 D13） | ✅ | 2026-09-20 |
| D5 | 图可视化库：~~AntV G6~~ → **ECharts + echarts-gl graphGL**（2026-09-22 用户指令，并入 D13） | ✅ | 2026-09-21 |
| D6 | AI 接入：LLM 配置页运行时可切换；Embedding 先用线上（预留本地切换端点）；DeepAgents + MCP 工具做结构化抽取 | ✅ | 2026-09-20 |
| D7 | 权限模型：所有者写入隔离 + 可见性共享读取（家庭内只读），从简不做复杂 ACL | ✅ | 2026-09-20 |
| D8 | 农历支持方案：lunar-python（后端纯函数封装） | ✅ | 2026-09-21 |
| D9 | Monica 数据迁移 ETL 方案 | ⬜ | — |
| D10 | 附件/照片存储（本地卷 vs S3 兼容） | ⬜ | — |
| D11 | **MCP 工具架构**：FastAPI 内 `/mcp` 前缀，Streamable HTTP，内外部 agent 共用同一工具清单与权限 | ✅ | 2026-09-20 |
| D12 | 模块治理：原子模块清单与依赖规则，事实源 `ARCHITECTURE.md`（先登记后实现） | ✅ | 2026-09-21 |
| D13 | 前端栈切换：Naive UI → **Element Plus**、图表框架 **ECharts**、关系图 **echarts-gl graphGL**（G6/3d-force-graph 移除）、新增 **geo** 模块与地图页 | ✅ | 2026-09-22 |
| D14 | 联系人地理位置：location 文本 + 高德地理编码（key 可配）+ 静态市县区坐标表降级，坐标缓存于联系人行 | ✅ | 2026-09-22 |
| D15 | 关系角色化：客观单边 + from_role/to_role/status，账号绑定联系人，登录视角动态推导，kinship 规则引擎出中文称谓与辈分 | ✅ | 2026-09-22 |

---

## D1 整体形态：全新自研 ✅

- **背景**：Monica（AGPL-3.0）已事实性停滞（最后稳定版 2024-05，最后提交 2025-08），需求差异大（中文本地化、关系图谱、AI 原生、细粒度权限均为核心改造点）。
- **备选**：① fork Monica 4.x 改造；② 全新自研。
- **决策**：全新自研，不 fork。
- **理由**：AGPL 协议传染（fork 后需整体开源且同协议）；Monica 的 PHP/Laravel 栈不延续；上述四项核心需求改造量合计接近重写，fork 只剩下负担。
- **影响**：技术栈完全自由；Monica 仅作为设计参考与数据迁移来源。

## D2 架构形态：前后端分离 + 单仓库 + 一体化部署 ✅

- **背景**：需求 R2（知识图谱交互）、R5（移动端高频使用）、R3（AI 流式交互）都对重交互客户端有硬性要求；用户已确定后端语言为 Python（AI/agent 生态最完整）。
- **备选**：① Python 一体化 UI（Django 模板 + htmx、NiceGUI、Reflex）；② Vue 3 SPA + Python API 前后端分离。
- **决策**：方案 ②，并把"分离"限定在 UI 技术栈与代码组织两个轴上，部署保持一体化。
- **理由**：
  1. **图可视化是心脏功能**：G6/Cytoscape 等图库均为 JS 原生生态，Python UI 框架包装 JS 库会造成抽象漏水，vibe coding 场景下风险最高；
  2. **移动端体验**：服务端驱动 UI 在触控、PWA 离线、弱网表现上先天不足，而"外出手机查人"是最高频场景；
  3. **语料量级**：Vue 3 + FastAPI 是 AI 代码生成语料最充足的组合之一，对纯 vibe coding 项目是关键选型指标；NiceGUI/Reflex 生态年轻，长期押注风险大；
  4. **Python 后端红利**：LangGraph 等 agent 生态、农历/中文处理库生态、Pydantic 同时服务数据契约与 AI 结构化抽取、Monica MySQL 数据 ETL 顺手。
  5. 一体化部署消除分离的运维成本：生产环境 FastAPI 直接托管前端构建产物，单进程、单域名、同源无 CORS；开发期 Vite 代理解决联调。
- **随本决策一并确定的技术组件**：
  - 后端：Python 3.12+ / FastAPI / Pydantic v2 / SQLAlchemy 2.x / Alembic / pytest（TDD）
  - 后端分层：`api / service / repository / model`，模块间仅经明确接口通信
  - 前端：Vue 3 / Vite / Pinia / Vue Router / vitest（TDD）/ PWA（桌面与移动同一套响应式代码）
  - 契约：FastAPI 自动产出 OpenAPI → `openapi-typescript` 生成前端类型，**API 即模块边界**，前端禁止绕过契约访问后端
  - AI 流式交互：SSE
- **仓库结构**：
  ```
  personal-crm/
  ├── backend/            # FastAPI 应用
  ├── frontend/           # Vue 3 SPA
  ├── docker-compose.yml  # 生产部署（FastAPI 单容器托管 API + 静态资源）
  ├── AGENTS.md           # 工程规范
  ├── PROJECT_BACKGROUND.md
  └── TECH_DECISIONS.md   # 本文档
  ```

## D3 数据库：PostgreSQL + pgvector 单库 ✅

- **背景**：需求 R2（关系图）与 R3（AI 原生：语义搜索、RAG、结构化抽取）对存储提出两类异构诉求——关系图谱查询与向量相似度检索。
- **备选**：① MySQL/PostgreSQL 纯关系库 + 外置向量库（Milvus/Qdrant/Chroma）；② PostgreSQL + pgvector 单库；③ 图数据库（Neo4j）+ 关系库组合。
- **决策**：**PostgreSQL + pgvector 扩展，单库承载结构化数据、关系图与向量**；关系图用邻接表存储，N 度关系查询用递归 CTE；不引入图数据库，不引入独立向量库。
- **理由**：
  1. pgvector 让向量与业务数据同库：AI 语义检索（"帮我找去年聊过孩子升学的朋友"）需要向量与联系人/备注/活动做关联过滤，同库同事务，免去跨库同步与两套运维；
  2. NAS 部署资源敏感，单容器单数据库是最省内存/运维的形态，pgvector 的 HNSW 索引在家庭数据量级（千级联系人、万级记忆片段）下性能冗余极大；
  3. 递归 CTE 承接 N 度关系查询在此量级下足够，图数据库是明显的过度设计；
  4. PostgreSQL 的 JSONB 可承接边缘联系人等半结构化扩展字段。
- **影响与注意**：
  - 向量列维度建表时固定，**Embedding 模型选型（D6）必须先于相应表结构落地**，后期换模型需做向量迁移；
  - 集成方式：`pgvector` 官方 Python 包 + SQLAlchemy 2（用法以官方文档为准，落地时用 context7 拉取最新版文档核对）。

## D6 AI 接入：DeepAgents + 运行时可配置 LLM + 线上 Embedding ✅

- **D6.1 内置 agent 框架 = DeepAgents（2026-09-20）**
  - LangChain 官方框架，`pip install deepagents`，基于 LangGraph 运行时；自带规划工具（todos）、虚拟文件系统后端、子代理调度；`create_deep_agent()` 返回编译后的 LangGraph 图，原生支持流式输出，与 SSE 方案（D2）衔接顺畅。
  - **设计约束（依工程规范强制）**：DeepAgents 尚在 v0.x 快速演进期，必须封装在自研 agent 服务模块内（`backend/agent/`），对外只暴露自研接口，业务代码禁止直接 import deepagents——保留框架可替换性，隔离上游破坏性变更。
- **D6.2 LLM 接入 = 系统配置页运行时配置（2026-09-20，用户定）**
  - LLM 的 provider / 端点 / 密钥 / 模型全部放入系统设置页面，**随时可通过页面切换**，不做死在环境变量或配置文件里；
  - **未配置的降级契约**：初始化时若未配置 LLM，系统正常启动、非 AI 功能完全可用；任何 AI 相关调用返回明确的"未配置 LLM"错误，前端据此引导用户去配置页完成设置（AI 是增强能力，不是系统可用性的前置条件）；
  - 后端影响：需要一个 **DB 支撑的运行时配置模块**（`settings`，尽早设计），LLM 客户端工厂每次调用读取当前配置；配置页应提供"连接测试"能力。
- **D6.3 Embedding = 先用线上端点，预留本地切换（2026-09-20，用户定）**
  - 现阶段 Embedding 走线上 API；架构上做 **provider 抽象，切换端点/供应商的入口留好**，后续可切本地模型（如 bge-m3）；
  - **与 D3 的联动约束**：pgvector 向量列维度固定，若切换的 Embedding 模型维度不同，须触发全量重嵌入迁移任务（后台 job 重算所有向量；家庭数据量级下为分钟级操作，可接受）。维度在首次配置 Embedding 时随模型确定。
- **D6.4 结构化抽取 = agent 抽取 + MCP 工具执行（2026-09-20，用户定）**
  - DeepAgents 负责意图理解与信息抽取，**动作执行（写待办、建联系人、记活动等）通过 MCP 工具完成**；
  - MCP 工具层的详细架构（工具粒度、安全与确认机制、server 形态、鉴权）为独立决策 **D11，是下一个核心议题**。

---

## D4 前端组件库：Naive UI ✅（已由 D13 取代，2026-09-22）

- **备选**：Naive UI / Element Plus。
- **决策**：Naive UI。用户将偏好决策授权给 agent（2026-09-20）。
- **理由**：themeOverrides 可深度映射自研设计 tokens（DESIGN.md「青瓷与印泥」方向），气质可控；TypeScript 原生；树摇体积小；中文文档完善；语料充足。Element Plus 视觉个性弱，深度换肤成本高。
- **配套**：设计系统见 `DESIGN.md`（风格锁定，全站统一修改）；tokens 单一来源 `frontend/src/design/tokens.ts`。
- **细化（2026-09-21，用户指令）**：前端组件一律**直接组合 Naive UI 组件**（n-card/n-list/n-tag/n-timeline/n-statistic 等）+ themeOverrides 映射 tokens，不重复造自研基础组件；仅 Naive UI 无对应形态时才自研（如头像、3D 图容器），自研部分样式仍只准消费 tokens。详见 `ARCHITECTURE.md` 第 5 节。

## D5 图可视化库：AntV G6 v5 ✅（已由 D13 取代，2026-09-22）

- **备选**：AntV G6 / Cytoscape.js。
- **决策（2026-09-21 Level 2 开工前复核定案）**：**G6 v5（npm 包 `@antv/g6` 5.x）**。已确认 v5 声明式 API：`new Graph({ container, data, node/edge style, layout, behaviors, plugins })` + `await graph.render()`，事件 `graph.on(NodeEvent.CLICK, ...)`，数据更新 `setData()`；与 v4 API 不兼容，任何旧示例代码不得直接照搬。
- **理由**：中文文档与国内社区最好，force/dagre 等布局与拖拽/点选交互开箱即用；家庭数据量级下性能冗余大。
- **约束**：图谱页配色只消费 design tokens（节点墨/灰、边浅灰、选中 seal 高亮，不引入多色 palette）。
- **主页 3D 关系图**：静态占位卡（用户 2026-09-21 定），3D 渲染选型（three.js 系 3d-force-graph 等）待主页迭代时定案。
- **主页 3D 关系图（2026-09-21）**：用户要求主页预留约一半空间给"3D 效果的空间节点关系图"。当前先以真实图数据占位预留，L2 动工前按铁律复核渲染选型（G6 v5 是否满足 3D 形态 / three.js 系 3d-force-graph 等）后定案，作为 D5 的补充决策。

## D6.3 落地细化：Embedding 维度与对账策略 ✅（2026-09-21）

- **维度固定 1024**：OpenAI text-embedding-3 系列支持 `dimensions` 参数截断、智谱 embedding-3 支持 `dims=1024`、本地 bge-m3 原生 1024——**换供应商不换维度**，embeddings 表列无需迁移；
- **关联方式**：`embeddings` 表以 `(entity_type, entity_id)` 元数据关联业务主键，不设硬 FK（业务记录删除由对账管线清理向量）；
- **变更处理**：`content_hash` 增量对账——内容未变跳过、变更重算、源消失清理、模型更换全量重建；管线幂等，设置页手动触发（个人量级秒级），实时钩子留作后续；
- **可见性**：向量化时快照源数据 D7 三件套，检索时仍按 readable_condition 过滤（私密数据向量对家人不可见）；
- **覆盖源**：联系人 / 活动 / 礼物 / 资金 / 备注（note 随 L3 补齐 API）。

## D8 农历支持：lunar-python ✅

- **备选**：lunar-python / lunar-javascript（前端向）/ 自研换算表。
- **决策**：后端引入 **lunar-python**（1.4.8，MIT，无第三方依赖），封装在 `app/modules/contacts/calendar.py` 纯函数模块内，不散落调用点。
- **理由**：lunar 系列库对农历/闰月/节气覆盖完整、维护活跃；纯 Python 实现 NAS 部署无二进制依赖；API 已实测（`Lunar.fromYmd(y,m,d).getSolar()`、`Solar.fromYmd(...).getLunar()`）。
- **约束**：闰月参数等 API 细节在实现时先查官方文档再写（工程铁律）；重要日期表结构（D8 农历三字段）此前已按此模型设计，无需变更。

## D7 权限模型：所有者写入隔离 + 可见性共享读取 ✅

- **背景**：需求 R4（夫妻共享、谁创建谁维护、另一方只读）。用户明确（2026-09-20）：本系统是家庭私有化部署，权限从简，不引入复杂角色/ACL 体系。
- **决策**：
  1. **写入隔离**：每条业务数据（联系人、待办、活动、备注等）带所有者（创建者），只有所有者可写。AI（内部 agent 或外部 MCP 客户端）一律以发起用户的身份执行写入，受同一约束；
  2. **读取共享**：每条数据带**可见性标志**（两档：私密 / 家庭可见）。私密仅所有者可读；家庭可见的数据，家庭其他成员一律**只读**；
  3. 不做按人授权、不做角色层级。未来确有需要再扩展，当前复杂度为零。
- **理由**：R4 的全部诉求由"所有者可写 + 家庭可见只读"两条直接覆盖；私有化家庭场景下，复杂权限是负资产，还会拖累 MCP 工具层与前端的设计。
- **细化决策（2026-09-20，用户定）**：
  - **跨用户"同一人"**：不做自动去重/合并，交由用户自行处理；防线前移到创建环节——无论手动创建还是 agent 创建，命中家庭范围内同名/近似同名时给出警告或输入框提示（agent 创建同样触发该检测，检测结果随提议返回给用户确认）；
  - **跨用户关系边**：允许建立；边归属创建者，读权限跟随两端数据可见性取交集；
  - 家庭组管理保持最简：邀请/移除即全部，不做多层家庭组织。

## D11 MCP 工具架构：FastAPI 内 `/mcp` 端点，内外部 agent 共用 ✅

- **背景**：D6.4 确定 AI 动作执行走 MCP 工具；用户进一步确定（2026-09-20）MCP 是系统的一等出口，对内对外共用，同一套权限。
- **决策**：
  1. **系统四类出口**：REST API、Web UI、Agent 对话接口（SSE 流式）、**MCP 端点**；
  2. **MCP server 实现于 FastAPI 应用内**，挂独立前缀 **`/mcp`**，传输协议采用 **Streamable HTTP**（agent 在服务端运行，不适用 stdio）；同进程部署，不增加容器；
  3. **双消费方共用一份工具清单**：内部 DeepAgents（`backend/agent/` 作为 MCP client 调用本系统工具）与外部 agent 客户端（配置端点 + 令牌接入，如桌面 AI 助手）；
  4. **工具档位**：
     - 查询类（搜联系人、查日程、查关系路径等）→ 直接执行；
     - 写入类（建联系人/待办/活动等）→ 默认进入**待确认队列**：agent 提议 → 用户界面确认 → 落库，AI 不静默写入家庭数据；
     - 边缘联系人自动创建为低风险档，可配置为免确认自动执行。
  5. **鉴权与权限**：MCP 端点复用用户体系（个人访问令牌），外部客户端以对应用户身份操作；权限判定与 REST API 共用同一套业务 service 层 + D7 规则，**禁止为 MCP 另设权限路径**。
- **理由**：内外共用一套工具层，避免"内部 agent 一套逻辑、外部集成另一套逻辑"的裂化；写入确认门是家庭数据的安全底线；FastAPI 同进程是最省资源的形态。
- **影响**：
  - 外部受信客户端的"直接写入"信任档位（跳过确认队列）留作后续可选配置，首版不做；
  - 工具清单随业务模块增量扩充；每个工具必须有明确的输入 schema、权限标注与单元测试（TDD）。
- **落地细化（2026-09-21，随 L4 首批实现定案）**：
  - MCP SDK 采用官方 `mcp` **v2**（`from mcp.server import MCPServer`，`streamable_http_app()` 挂载，宿主 lifespan 内启动 session_manager）；
  - **工具单一实现源**：`app/modules/ai/registry.py` 的注册表是工具的唯一实现；`/mcp` 端点与内部 agent 是它的两个出口适配器（内部 agent 同进程直调注册表，不走自连 HTTP）——符合"共用一份清单与权限"，避免自连网络与鉴权循环；
  - 写入确认的落库形态：写入类工具不阻断 agent 流，调用即入 `pending_actions` 队列并返回"待确认"提示；用户在对话浮层/待确认面板确认后以**提议人身份**执行（失败原因记入 result，不静默）；
  - 鉴权过渡态：`/mcp` 门卫当前复用 JWT，个人访问令牌（user_tokens）签发 UI 后补。

## D12 模块治理：原子模块清单与依赖规则 ✅

- **背景**：开发中发现"边写功能边长模块"会导致模块边界与依赖方向失控（2026-09-21 用户纠偏：先把原子模块与数据表依赖理清，再写代码）。
- **决策**：以 `ARCHITECTURE.md` 为结构事实源——原子模块清单、表归属、依赖方向图、五条依赖规则（表写权独占 / 只读 JOIN 白名单 / service 唯一门面 / 依赖单向无环 / **先登记后实现**）。新增模块先登记再建包。
- **理由**：模块边界错误的事后修复成本远高于先登记；架构图的可见性让每次"新模块"都经过一次设计审视，符合 AGENTS.md 的高内聚低耦合红线。

## D13 前端栈切换：Element Plus + ECharts/graphGL + geo 地理模块 ✅（2026-09-22，用户指令）

- **背景**：用户 2026-09-22 指令——图表框架改用 **ECharts**、前端组件框架改用 **Element Plus**（用户先口误说 Element UI，随后自行更正为 Element Plus），关系图用 **graphGL**（即 echarts-gl 的 `graphGL` 系列，WebGL 加速 3D 力导向图）渲染，另加 **geo choropleth + scatter 地理空间散点图**。本条替代 2026-09-21 的 Naive UI 指令与 D5 的 G6 选型；此前 L2 已按 G6 落地的 GraphPage 一并迁移。
- **决策**：
  1. **组件库 = Element Plus**（Vue 3 唯一对应的 Element 系；Element UI 仅支持 Vue 2）。主题走 **Element Plus CSS 变量映射层**：在 `design/` 新增映射文件，把 `--el-*` 变量统一翻译为 design tokens（单一事实源不变），组件深度换肤仍收敛在 tokens 一处；
  2. **图表框架 = ECharts（锁 5.x，echarts-gl 2.x 的兼容面）+ echarts-gl**；全站图表只经 ECharts，禁止再引入第二套图表栈；
  3. **关系图 = echarts-gl `graphGL`**（force3D 布局、WebGL 渲染）：主页右半区（原静态占位卡）与 GraphPage 统一迁移，`@antv/g6` 与探索性安装的 `3d-force-graph` 卸载；
  4. **新模块 geo**（登记于 ARCHITECTURE.md）：地理编码 provider 抽象 + 中国地图数据源，支撑地图页与联系人位置解析（细节见 D14）。
- **理由**：ECharts 是中文生态最厚、语料最足的图表栈，graphGL 提供 3D 空间感且与 ECharts 同栈零额外依赖；Element Plus 与 ECharts 组合语料充足，符合 D2 的"语料量级"选型指标。
- **影响**：
  - `AGENTS.md` 第"前端风格统一"节与 `ARCHITECTURE.md` 第 5 节同步改口径为 Element Plus + ECharts；
  - 全站 ~17 个文件 n-* 组件一次性替换（切换不留中间态）；`useMessage` → `ElMessage`，`themeOverrides` 装配移除；
  - Naive UI 按需导入的工程加固项改写为 Element Plus（unplugin-vue-components）+ ECharts 按需注册。

## D14 联系人地理位置：地理编码 + 静态表降级 ✅（2026-09-22）

- **需求**：地图页（geo choropleth + scatter）需要联系人的经纬度；联系人在表单里只填**位置文本**（如"上海市浦东新区"），坐标由系统解析。
- **决策**：
  1. **口径勘误**：地址文本 → 坐标是高德**地理编码**接口（`/v3/geocode/geo`）；"逆地理编码"（regeo）是坐标 → 地址，方向相反，本需求用前者；
  2. **provider 抽象**（geo 模块内）：`resolve(location_text) → {lng, lat, level, source} | None`；实现两档——`AmapGeocoder`（settings 配了 key 才启用，HTTP 超时短、失败静默降级）→ `StaticTableGeocoder`（geo 模块内置 `cities.json`：公开行政区划数据整理的省/市/区县中心坐标，去"市/区/县"后缀匹配）；
  3. **坐标缓存于联系人行**：`location`（文本）、`location_lng` / `location_lat` / `location_source`（amap / static / none）四个可空列；联系人保存时 location 变更才重算，未变不触发外部调用；
  4. **key 管理**：高德 key 放 settings 模块（KEY_GEO_AMAP），掩码回显 + 测试按钮，与 LLM/Embedding 同模式；未配置不阻塞任何功能（地图页静态表仍可用）。
- **理由**：家用量级下高德个人 key 免费额度足够；静态表兜底保证零配置可用与离线可用；缓存到行避免每次打开地图页重复请求外部 API。
- **约束**：静态表精度为市区级（直辖市/省会到区县级），精度不足时地图撒点落在市中心，属可接受的降级形态；地图数据（中国 GeoJSON）用 DataV.GeoAtlas 开放数据，vendor 进前端 assets，不运行时拉取。

## 待决事项备注



- D4 组件库、D5 图可视化库需在 frontend 脚手架搭建前定案；D8 农历、D9 迁移、D10 附件存储可在架构落地过程中逐项决策。
- **vCard 导入导出（2026-09-21 暂缓）**：曾评估用户点名的 python-vcard4——README 自述"远未可用"、无发布版、GPL-3.0（与 D1 防传染原则冲突）、且只解析不生成，不可用；备选 vobject（Apache-2.0）仅完整支持 3.0。需求延后，重启时需重新调研（含导出 4.0 自研序列化器的可行性）与联系人模型扩展（联系方式表/称谓/职位/UID）。
- **建议下一议题：数据模型设计**——联系人 / 双层模型 / 关系边 / 所有权与可见性的 schema（含 D7 影响中的跨用户去重与跨用户关系边），被 D3/D7/D11 共同依赖，定案后即可开始工程脚手架。
- 决策新增条目时在"决策总览"表登记，并在下方补充独立小节（背景/备选/决策/理由/影响五段式）。

## D15 关系模型角色化：客观单边 + 视角推导 + 称谓引擎 ✅（2026-09-22）

- **背景**：用户提出现有关系模型不满足需要（2026-09-22，附外部参考方案）：家庭关系需要"爸爸/舅舅/岳父"级别的角色语义与称谓/辈分推导，而非仅有类型标签。
- **决策**（采纳参考方案核心，三处按本系统现状调整）：
  1. **客观关系单边存储**：relationship 加 `from_role / to_role`（语义：from 是 to 的 from_role；to 是 from 的 to_role）与 `status`（active/former）；夫妻只存一条边（from_role=husband, to_role=wife），亲子父/母→子/女，兄弟姐妹按长幼存（elder_brother→younger_brother）；查询时从当前节点在边的哪一端解析出目标角色，**不存任何"某人眼中的关系"**；
  2. **系统类型 + 自定义字典并存**：relationship_types 加 `is_system`（结构化类型标记）与 `kind`（parent/spouse/sibling），内置三类系统类型；用户自定义类型保留现状能力，role 为空不参与推导（兼容旧数据零破坏：role 空 → 退回现有句式归一）；
  3. **复用 contacts/families，不引入 person/family_space 新表**：contacts 已是纯自然人节点，`users.contact_id`（可空）完成"账号 → 我是谁"绑定；家庭空间即现有 families；
  4. **主键保持 BIGINT**，不切 UUID；
  5. **称谓引擎 `graph/kinship.py`（纯函数）**：角色路径 + 性别 → 中文称呼 + 辈分差；规则表覆盖直系/兄弟（含长幼）/配偶系/孙辈/侄甥约 40 条 + 归一（elder/younger sister → 姑姑/姨妈类）+ 兜底；**规则只存事实，称呼=规则引擎推导**；自定义称呼覆盖（user_relation_label 表）后置；
  6. 录入形态：系统类型建边时角色用受控下拉（按 kind 联动值域），不做自由文本。
- **理由**：客观单边避免数据冗余与不一致；角色显式化让同性婚姻/继亲（partner）可表达；纯函数引擎可独立测试；复用现有表让迁移面最小。
- **影响**：存量边迁移时按旧字典标签映射角色（能映射的映射，不能的留空走兼容句式）；图谱/详情/AI 工具同步升级为称谓句式；users 绑定后 AI 的"我"语义可解析。

