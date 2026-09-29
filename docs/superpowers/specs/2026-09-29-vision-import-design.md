# 视觉导入：对话框传图 → 识别 → 确认落库 设计

> 日期：2026-09-29｜状态：待用户审阅
> 上游：`PROJECT_BACKGROUND.md`（R3 AI 原生录入）、`ROADMAP.md` Level 4「截图导入」、`TECH_DECISIONS.md`（D6 AI 接入、D11 MCP、D18 图片存储）
> 本文是实施计划的输入；批准后进入 `writing-plans`。

## 1. 目标（用户原话拆解）

1. 图片在**对话框上传**（范围已定：只做对话框入口，不做页面/独立入口）。
2. 解析用**与 agent 同一个 LLM**——不引入第二个模型配置项。
3. 模型**不支持多模态 → 明确报错**（不是模糊的「处理失败」）。
4. 解析完成后**硬中断**：生成写入提议进确认队列，**未确认绝不落库**（复用现有 `pending_actions` 机制，不引入 LangGraph interrupt）。

## 2. 现状核对

| 需求 | 现状 |
|---|---|
| 上传通路 | ✅ `POST /uploads/temp` + `storage`（扩展名/可解码/体积校验，本人临时区隔离，防路径穿越） |
| 确认队列 | ✅ `pending.propose/approve/reject` + `EXECUTORS` 执行器表 + AgentChat 确认面板（现有 `create_task`/`create_activity` 走此路） |
| 联系人写入 | ✅ `contacts_service.create_contact`（同名检测 D7：命中且未确认 → 不落库） |
| 联系人字段 | ✅ `ContactBase` 已有 phone/qq/wechat/email/organization/school_name/bio/location，名片信息全有落点（前端名册表单未做电话输入是既有缺口，本期不动） |
| 多模态消息 | ❌ `ChatIn` 只有文本 `message`；`stream_agent` 只构造纯文本 content |
| 视觉降级 | ❌ 上游异常进通用「对话处理失败」错误帧，无专属性提示 |
| `create_contact` 工具 | ❌ 工具注册表无此项 |
| 确认面板可读性 | ⚠️ `payloadText` 直接拼英文 key（`last_name: 王`） |

## 3. 关键决策（登记为 TECH_DECISIONS D21）

1. **同模型**：视觉解析用当前配置的 LLM，不新增「视觉模型」配置。支持与否**以真实上游报错为准**（被动检测），不做模型名启发式判断——启发式不可靠，误判比报错更糟。
2. **直通 agent**：图片作为多模态消息内容进入现有 agent，由它决定调 `create_contact`（或先 `search_contacts` 查重）。不建第二条独立抽取管线——那会绕开工具注册表与 /mcp，形成两套 LLM 通路。
3. **确认走既有队列**：「硬中断」= 写操作只能经 `pending` 队列、确认后才落库。与 `create_task`/`create_activity` 同一红线，不引入第二套确认机制。

## 4. 后端设计

### 4.1 契约与图片校验

- `ChatIn` 增加 `images: list[str] | None = None`——temp_path 列表，**最多 1 张**（超限由 pydantic 校验拒绝，422）。
- chat 端点内逐项校验：
  - 路径必须形如 `tmp/{user_id}/…` 且 `user_id == 当前用户.id`（他人路径 404，不泄露存在性）；
  - `storage.resolve_within_root` 解析（防 `../` 穿越），不存在 404；
  - 读取 bytes；MIME 按扩展名映射（`.jpg/.jpeg→image/jpeg`、`.png→image/png`、`.webp→image/webp`，与 `storage.ALLOWED_EXTENSIONS` 一致）。
- 临时文件**用后不删**：临时区本有 lifespan 过期清理（`cleanup_temp`），重复利用既有机制。

### 4.2 runner：多模态消息

- `stream_agent(db, user, llm, message, session_id, images=None)`：
  - `images` 非空时，输入消息 content 为分段列表：
    `[{"type":"text","text":message}, {"type":"image_url","image_url":{"url":"data:{mime};base64,{b64}"}}]`
  - 纯文本时维持现状（OpenAI 兼容端点两种形态都接受）。
- 历史回显：`_to_history_messages` 对分段列表 content 的消息，文本前加 `［图片］` 标记；**图片本体不进历史**（MVP 取舍——checkpointer 里存的是多模态消息，但历史渲染只回文本）。

### 4.3 视觉不支持的降级

- runner 内捕获上游异常：**本次请求带图** 且上游抛 4xx → SSE 结束帧改为
  `{"type":"error","code":"vision_unsupported","message":"当前模型不支持图片输入，请在设置页换用支持视觉的模型（上游：<截断 200 字的原始错误>）"}`。
- 判据是**请求特征**（带图）而非错误文本匹配；不带图的 4xx 仍走通用兜底帧。
- 已知误报：带图时个别非视觉原因的 4xx（如上下文超限）也会得到此文案——靠附带的上游摘要甄别，接受此取舍。

### 4.4 新工具 `create_contact`（risk=write_queue）

- `CreateContactArgs`（model_validator：姓/名/昵称至少一项，照 `ContactCreate.validate_name_presence`）：
  `tier: "direct"|"edge" = "direct"`、`last_name`、`first_name`、`nickname`、`organization`、`phone`、`qq`、`wechat`、`email`、`school_name`、`bio`、`location`（其余全可选）。
- `run` → `pending.propose(db, user, "create_contact", payload)` + 提示文案（照 `create_task` 的「已生成提议（编号 N，待确认）」模式）。
- `EXECUTORS["create_contact"]` → `contacts_service.create_contact(db, requester, ContactCreate(**payload))`（gender=unknown、visibility=family 走默认）：
  - `created=True` → `result = {"ok": True, "message": "联系人已创建（id=N）：展示名"}`；
  - `created=False`（同名拦截）→ `result = {"ok": False, "error": "同名提醒：…已存在于…的名册，未创建。可拒绝此提议，或去名册处理"}`——**不用 `confirm_duplicate=True` 绕过同名保护**。
- MCP：`create_contact` 经 `ALL_TOOLS` 自动暴露给 `/mcp`（工具单一注册表），外部 agent 提议走同一队列，零额外代码。

### 4.5 系统提示词增补

`SYSTEM_PROMPT` 追加一条：
> 用户发来名片/聊天截图要求录入时：先用 search_contacts 查同名，再调 create_contact 生成提议（需用户确认后生效）；图里没有的字段留空，禁止编造。

## 5. 前端设计（AgentChat）

- **上传**：输入区加 📎 按钮（隐藏 `<input type="file" accept="image/*">`）+ 对话区**拖拽**上传；选中/拖入即 `api.uploadTemp` → 本地 object URL 缩略图预览（可点 × 移除）；**只保留最后一张**（新选替换旧选）。上传失败（超限/类型不符）→ ElMessage 报错并清空。
- **发送**：`aiApi.chat(text, sessionId, onEvent, images?)`——第 4 参可选；请求体带 `images: [tempPath]`；发送成功后清空预览；用户气泡内渲染缩略图（本地 object URL）。
- **错误**：`code === "vision_unsupported"` → 气泡显示后端 message（含设置页引导）。
- **确认面板**：`tool_name === "create_contact"` 时用中文标签映射渲染 payload（姓名 / 昵称 / 电话 / 单位 / 邮箱 / 微信 / QQ / 院校 / 所在地 / 备注），其余工具维持现有 `payloadText`。
- **历史**：`［图片］` 文本标记随历史消息照常显示（无图）。

## 6. 测试

后端（新增 `tests/test_ai_vision.py`；`tests/test_ai_tools.py` 扩充）：
1. chat 带 temp_path → stub 捕获 agent 输入：content 为多模态分段、data URI 前缀与 MIME 正确；
2. 他人 temp_path / `../` 越界路径 / 不存在文件 → 404；
3. `images` 超 1 张 → 422；
4. stub 上游抛 4xx 且带图 → error 帧 `code=vision_unsupported` 且文案含设置页引导；不带图 → 通用错误帧；
5. 带图消息载入历史 → 文本带 `［图片］` 标记；
6. `create_contact` 工具 run → 队列出现提议且 payload 形状正确；
7. approve 执行：无同名 → 落库且 phone 在；同名 → `result.ok=False` 且不产生第二条联系人。

前端（新增 `tests/agentChat.spec.ts`）：
1. 选图 → 调 `uploadTemp` → 预览出现；
2. 发送带图 → 请求体含 `images`；
3. `vision_unsupported` 错误帧 → 气泡出现引导文案；
4. `create_contact` 提议 → 中文标签渲染；
5. 其他工具提议 → 维持英文 key 拼接。

## 7. 文档登记

- `TECH_DECISIONS.md`：新增 **D21**（视觉导入三原则：同模型 / 直通 agent / 确认走既有队列）；
- `ARCHITECTURE.md`：第 4 节 `/ai` 行补 `ChatIn.images` 与 `create_contact`；第 1 节 ai 模块职责补「视觉导入」；
- `DESIGN.md`：助理页上传交互（📎/拖拽/缩略图/一次性预览）；
- `ROADMAP.md`：Level 4「截图导入」标 ✅。

## 8. 不做（本期明确排除）

- 确认前编辑提议字段——拒绝后重说；升级路径：`PATCH /ai/pending/{id}`；
- 多图/批量导入——升级路径：放宽 `images` 数量并逐张提议；
- 独立页面/名册页入口（用户已否）；
- OCR 兜底（无视觉模型时的本地识别）；
- 名册表单的电话输入（既有缺口，另行处理）；
- 历史消息回显图片本体。

## 9. 风险与取舍

- **解析质量依赖模型**：视觉模型认错字无法杜绝；确认队列本身是兜底——提议内容确认前完全可见。
- **消息体积**：1 张图 base64 后约 1–2MB，OpenAI 兼容端点可承载；体积上限由 `storage.MAX_IMAGE_BYTES` 在入临时区时把住。
- **4xx 判据误报**：带图 + 上游 4xx 一律提示「可能不支持视觉」，可能掩盖个别其他 4xx——靠附带的上游原始错误摘要甄别。
