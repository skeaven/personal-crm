# 前端设计系统（风格锁定文档）

> 依据 taste-skill（design-taste-frontend + minimalist-ui）流程产出。**本文件是全项目前端视觉的唯一事实源**：新组件必须使用本 tokens；改风格必须改这里并全局生效，禁止单组件私自改色/改圆角/改字体。
> 组件库：**Element Plus**（D13，2026-09-22 指令，替代原 Naive UI），主题经 `frontend/src/design/element-plus.css` 的 CSS 变量映射层消费本 tokens；图表 = ECharts（锁 5.x）+ echarts-gl，色板经 `design/theme.ts` 的 chartPalette。
>
> **版本历史**：v1「青瓷与印泥」（冷调，2026-09-20 上午）→ v2「家书暖笺」（暖调，2026-09-20）→ **v3「纸墨」（现行，2026-09-20）**：用户两轮反馈后依据 taste-skill 全局重设计为极简现代。v2 的暖米+可可+深咖配色命中 design-taste-frontend 的 premium-consumer 调色禁令（AI 默认暖工艺配色），v3 转向"纯单色 + 单一彩色瞬间"。

## 设计方向：纸墨（premium utilitarian minimalism）

**Design Read**：自托管家庭关系管理产品 UI，受众为家庭用户；Notion/Linear 式文档极简语言。Dials：VARIANCE 5 / MOTION 3 / DENSITY 3。

**核心原则：色彩是稀缺资源。** 界面由纸（白与骨灰白）、墨（近黑）、1px 极浅灰结构线构成；**印泥红是全站唯一的彩色瞬间**——只出现在品牌印章、危险操作、私密标记与（未来的）日期提醒上，禁止任何装饰性使用。层级靠字号、字重与留白表达，不靠颜色和阴影。

**自查记录**（对照两份 skill 的禁令清单）：无暖米底（已弃）、无衬线正文（serif 仅存于印章 logo 字符，属 logo 豁免）、无纯黑纯白（#1A1A1A / 结构线 #EAEAEA）、无重阴影（唯一阴影是悬停 0.04 透明度）、无渐变、无胶囊大容器、圆角全站两档 6/10、无弹簧动效（MOTION 3：缓出曲线）、无 emoji、无 em-dash、品牌保留（印章「记」）。通过。

## Tokens（单一来源：`frontend/src/design/tokens.ts`，启动时注入 CSS 变量）

### 色彩
| Token | 值 | 用途 |
|---|---|---|
| `--crm-canvas` | `#FFFFFF` | 页面与内容面画布 |
| `--crm-bone` | `#F7F7F5` | 骨灰白：侧边栏底、行悬停底 |
| `--crm-ink` | `#1A1A1A` | **墨色**：正文 + 主按钮/开关/激活态（禁纯 #000） |
| `--crm-ink-hover` | `#333333` | 墨色 hover |
| `--crm-muted` | `#787774` | 次级文字、图标、退出按钮 |
| `--crm-line` | `#EAEAEA` | 结构线：全站唯一边框/分割色（1px） |
| `--crm-seal` | `#B93C2B` | **印泥红（降饱和）**：印章 logo、危险、私密标记、日期提醒。全站唯一彩色，禁止装饰性使用 |
| `--crm-seal-soft` | `#FDEBEC` | 印泥红浅底 |

语义色（低饱和）：success `#346538`，warning `#956400`，info `#1F6C9F`。

### 字体（保持用户要求的大字号）
| 角色 | 字体栈 | 用途 |
|---|---|---|
| body/display | `-apple-system,"PingFang SC","Microsoft YaHei","Helvetica Neue",sans-serif` | 全站单一家族；展示层级用字重 600 + 紧字距 `-0.02em`（`.crm-display`） |
| seal | `"Songti SC","STSong",serif` | **仅**品牌印章「记」字符（logo 豁免） |

字号阶梯：12 / 13 / **15(正文基准)** / 16 / **17(名册姓名)** / 20 / **32(页题)** / 44(大数字)。Element Plus 全局 `--el-font-size-base=15px`（映射层注入）。禁止换字体家族做强调（用同族 italic/bold）、禁止全大写眉标。

### 形状与层次
- 圆角：控件 `6px`，卡片/浮层 `10px`（利落，禁胶囊大容器）。
- **无阴影**：层次靠 1px `#EAEAEA` 边框与留白；唯一例外是悬停浮起 `0 2px 8px rgba(0,0,0,0.04)`。
- 名册容器：`1px solid line` + 10px 圆角 + 白底（minimalist-ui 卡片规则）；行间发丝线。

### 动效（MOTION 3，全部定义于 tokens.motion）
- 常规过渡 `200ms cubic-bezier(0.16,1,0.3,1)`：行悬停只变底色（bone）、侧栏项、按钮 hover。
- 按压反馈：`.n-button:active { scale(0.98) }`。
- 内容进入 `crm-rise`（600ms 缓出淡入 12px）：全站唯一非触发动效。
- 禁止：弹簧回弹、入场动画瀑布、每卡片 hover 特效。`prefers-reduced-motion` 全局尊重。

### 布局
- 桌面：左侧 208px 骨灰白轻侧栏（1px 右边线、墨色文字、激活项 `#ECECEB` 底）；页题（32px 墨色紧字距）直接落在内容区。
- **页面内容宽（2026-09-25 统一，取代 09-24 的"详情页 80% 阅读列"）**：全站唯一口径是全局原语 `.crm-page` —— `width:100%` + `max-width: var(--crm-content-max-width)`（1080px）+ `margin:0 auto`（**居中**）。列表页、详情页、助手页一律共用；**各页面禁止自行声明宽度**，改口径只改 `.crm-page` 一处。窄屏自动退化为满宽。
- **画布型布局页豁免**：主页 / 图谱 / 地图用 `.crm-page--full`（`max-width:none`）占满内容区 —— 3D 力导向图、地图与主页卡片网格需要横向空间，不参与统一收窄。
- **数据录入形态（2026-09-25 统一）**：表单一律 `el-dialog` **居中弹窗**（`width="480px"` + `destroy-on-close`），**不用右侧抽屉**；字段多的表单在窗内滚动（`.el-dialog__body { max-height: calc(100vh - 240px) }`），header/footer 固定，弹窗整体上移 `--el-dialog-margin-top: 7vh`；窄屏 <560px 宽度改 `calc(100vw - 32px)`。页脚用组件原生 `#footer`（取消 + 主操作），不自建页脚容器。
- 移动（Level 5 专项打磨前基线）：侧边导航折叠为抽屉（`.menu-drawer`，导航专用，**不是**数据表单，不受上述弹窗形态约束）；列表行降为两行式。
- 名册式列表：行高 54px，姓名列 17px 加重，行悬停 bone 底。

## 组件规则

1. 一律通过 Element Plus 组件 + CSS 变量映射层实现，自定义 CSS 只做布局与名册行；
2. 任何新页面先套 `AppLayout` + `.crm-page` 内容容器（宽度唯一口径，见布局节）+ 页题（`.crm-display`）+ 名册行结构 + `crm-rise`；
3. 状态徽标：中性信息（边缘层级）用 bone 底 + muted 字；**私密/提醒类才允许用 seal 红系**（sealSoft 底 + seal 字）；
4. 空状态一句直白中文文案 + 主操作按钮，不放插画；
5. 图标：`@vicons/ionicons5` 线性风格，16/20 两档，全站统一描边。

## 图片与往来时间线（2026-09-25）

- **缩略图**：上传器网格与时间线卡片封面同为 96px 方形（`object-fit: cover`，1px `--crm-line` 描边、`--crm-radius-control` 圆角）。
- **封面标记**：上传器首张左上角 `--crm-seal` 底白字小标「封面」——印泥红用于「当前主图」这一状态标记。
- **大图**：查看器内按容器宽度铺满、`object-fit: contain` 不裁切，最大高 60vh；底部居中「上一张 / 序号 / 下一张」。
- **时间线卡片**：操作按钮（查看详情/删除）右对齐、`size="small"`；删除走 `el-popconfirm`；金额用 `tabular-nums` 等宽数字。
- **Tab 标签内的「记一笔」**：`text` 按钮嵌在标签里，带 `@click.stop`（点它不切换 Tab）。

## 助理页（2026-09-27）

- **两栏栅格**：`grid-template-columns: 220px 1fr`，栅格间距 16px；左侧会话列表定宽，右侧对话区自适应（`.chat-card` 用 `--crm-canvas` 底 + `--crm-line` 描边 + `--crm-radius-float` 圆角）。
- **会话列表项**：44px 高、悬停与选中同为 `--crm-bone` 底、标题单行省略；列表时间只到「日」；删除走 `el-popconfirm`。
- **窄屏 <720px**：退化为上下排列（列表在上、对话区在下），`grid-template-rows: auto 1fr`。
- 助理为导航独立入口（`/assistant`），不再有全局悬浮球。

## 搜索页（2026-09-29）

- **入口**：导航独立一项（`/search`，排在「助理」之后），页面骨架沿用 `.crm-page`（D17）。
- **触发方式**：回车或点按钮才发请求，不做输入即搜——语义搜索每查一次都要调一次 embedding 接口。
- **结果分组**：按实体类型固定顺序（联系人 / 活动 / 礼物 / 资金 / 备注）；组标题 13px `--crm-muted`，条目 14px、行间 `--crm-line` 下边框。
- **可点性**：只有联系人条目可点（悬停 `--crm-bone` 底 + 「查看」提示）并跳 `/contacts/:id`；活动/礼物/资金/备注暂无详情页，只展示内容。
- **提示态**：配置类错误（未配 Embedding）用 `--crm-seal-soft` 底 + `--crm-seal` 文字的提示条，附「去设置页」入口；搜到空结果则提示先在设置页重建索引。

## 设置页 · 外部接入（MCP 令牌，2026-09-29）

- **区块结构**：沿用设置页既有的 `.section-head` + `.form-card`，位置在「地图（高德）」与「我是谁」之间。
- **列表项**：名称 14px + 元信息 12px `--crm-muted`（签发日 · 最后使用，只到「日」），行间 `--crm-line` 上边框；吊销走 `el-popconfirm`。
- **一次性明文**：签发后用 `el-dialog`（480px）展示明文 + 复制按钮，文案明说「只显示这一次」；列表任何位置都不出现明文或哈希。

## 锁定规则（用户指令，2026-09-20）

- 风格一经选定不再摇摆；**要改只能全站一起改**：改 `tokens.ts` / `theme.ts` 一处生效全局，出现"某个页面颜色不一样"即为缺陷（v2→v3 改版即按此机制执行）；
- 新组件合并前自查：颜色/圆角/字体/动效是否全部来自 tokens，有无引入第二个彩色、新的阴影档位。
