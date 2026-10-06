# L3 提醒引擎实施计划（2026-09-23 需求，随 ROADMAP 剩余清单第 1 项）

## 目标
系统从"被动查"升级为"主动提醒"：到期/临近的事项（重要日期、任务、还款）自动生成
应用内提醒，用户登录后可见、可逐条/全部标记已读。邮件通知本期不做（个人部署无 SMTP
基础设施，接口留好 provider 位）。

## 设计决策（对齐既有架构）
1. **模块归属**：新 `reminders` 聚合（dashboard 纯消费叶子不合适——它要写表），
   位置 `app/modules/reminders/`，登记 ARCHITECTURE.md（依赖：contacts/records/funds
   的只读查询 + settings 读取，不依赖 dashboard/ai）。表 `reminders` 归它独占。
2. **生成策略 = 幂等重建，非逐条 append**：每次扫描以"业务来源 (source, ref_id,
   user_id, due_date)"为唯一键 upsert——已存在未读的跳过、窗口内已读的不再复活、
   源头消失（任务完成/日期删除/资金结清）的未读提醒清理。个人量级（百级）全量重建
   每次毫秒级，比"记状态防重发"的状态机简单一个数量级且天然正确。
3. **扫描节奏 = 进程内 asyncio 后台任务**（NAS 友好，不引 celery/APScheduler）：
   lifespan 启动，每 1 小时扫一次 + 启动扫一次；每次扫描开短会话、异常吞掉记日志，
   绝不影响主服务。留 `POST /reminders/scan`（所有者触发，便于测试）。
4. **窗口口径（与 dashboard 待办四桶同源，不重复实现口径）**：
   - 重要日期：复用 `contacts_service.upcoming_date_reminders`（含农历/滚动明年）
   - 任务：due_at 未完成且 ≤ due_date+0（当天与过期各一条语义不同——统一"过期 N 天"
     一条，未过期进窗口 7 天）
   - 还款：funds 未结清且 due_at 进入窗口（7 天）或已逾期
   - **活动**：不进提醒（有自己的待办桶且临近活动在主页已可见，避免噪音）
5. **邮件通知 = provider 接口预留**：`channel` 列 + Notifier 协议（应用内实现落库，
   EmailNotifier 空实现 + TODO），本期只落应用内。
6. **前端**：侧栏"提醒"入口 + 顶栏红点徽标（未读数）+ 提醒页（全部/未读过滤、
   逐条/全部已读、点击跳转来源）。

## 任务分解（TDD，每步红灯→绿灯）
1. migration：`reminders` 表（id, user_id, family_id, source, ref_id, title, due_date,
   days_left 快照, contact_id nullable, channel, read_at nullable, created_at；
   UNIQUE(user_id, source, ref_id, due_date)）
2. models + repository（upsert/未读数/标记已读/清理失效）
3. service.scan_user：三源装载（复用 contacts/dashboard/records/funds 既有 service
   只读函数）→ 幂等 upsert → 返回统计
4. scheduler.py：asyncio task，1h 间隔全家庭扫描（family 内逐用户，权限口径按用户）
5. api：GET /reminders（未读/全部）、POST /reminders/{id}/read、POST /reminders/read-all、
   GET /reminders/unread-count、POST /reminders/scan
6. main.lifespan 挂载 scheduler；测试：三源生成、幂等（重复扫描不重发）、已读不复活、
   源头消失清理、权限隔离
7. 前端：types/api、提醒页（路由 /reminders）、顶栏铃铛 + 未读徽标
8. 文档：ARCHITECTURE 登记、ROADMAP 状态更新、TECH_DECISIONS D22

## 明确不做（本期）
- 邮件/短信真实发送（provider 位预留）
- 浏览器 Web Push
- 提醒的自定义窗口（沿用各源的既定窗口）
