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
- 桌面：左侧 208px 骨灰白轻侧栏（1px 右边线、墨色文字、激活项 `#ECECEB` 底），内容区最大宽 1080px 左对齐；页题（32px 墨色紧字距）直接落在内容区。
- 移动（Level 5 专项打磨前基线）：侧边导航折叠为抽屉；列表行降为两行式。
- 名册式列表：行高 54px，姓名列 17px 加重，行悬停 bone 底。

## 组件规则

1. 一律通过 Element Plus 组件 + CSS 变量映射层实现，自定义 CSS 只做布局与名册行；
2. 任何新页面先套 `AppLayout` + 页题（`.crm-display`）+ 名册行结构 + `crm-rise`；
3. 状态徽标：中性信息（边缘层级）用 bone 底 + muted 字；**私密/提醒类才允许用 seal 红系**（sealSoft 底 + seal 字）；
4. 空状态一句直白中文文案 + 主操作按钮，不放插画；
5. 图标：`@vicons/ionicons5` 线性风格，16/20 两档，全站统一描边。

## 锁定规则（用户指令，2026-09-20）

- 风格一经选定不再摇摆；**要改只能全站一起改**：改 `tokens.ts` / `theme.ts` 一处生效全局，出现"某个页面颜色不一样"即为缺陷（v2→v3 改版即按此机制执行）；
- 新组件合并前自查：颜色/圆角/字体/动效是否全部来自 tokens，有无引入第二个彩色、新的阴影档位。
