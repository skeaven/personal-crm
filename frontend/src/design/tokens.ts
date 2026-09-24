/**
 * 设计 tokens 单一来源（DESIGN.md v3「纸墨」极简现代）。
 * 全站颜色/圆角/字体/阴影/动效只能从这里取值；改风格只改此文件，全局生效。
 * v3（2026-09-20）：依据 taste-skill（design-taste-frontend + minimalist-ui）由「家书暖笺」全局改为
 * 极简现代：暖工艺配色被弃用（premium-consumer 调色禁令），转向纯净中性单色 + 单一印泥红瞬间。
 */

export const tokens = {
  color: {
    /** 纯白画布（禁纯 #fff 用于文字，画布允许） */
    canvas: '#FFFFFF',
    /** 骨灰白：侧边栏、行悬停等次级面 */
    bone: '#F7F7F5',
    /** 近黑墨色：正文与主按钮（禁纯 #000） */
    ink: '#1A1A1A',
    /** 墨黑 hover 档 */
    inkHover: '#333333',
    /** 次级文字灰 */
    muted: '#787774',
    /** 结构线：全站唯一的 1px 边框色 */
    line: '#EAEAEA',
    /** 印泥红（降饱和）：全站唯一彩色瞬间——品牌印章/危险/提醒，禁止装饰性使用 */
    seal: '#B93C2B',
    /** 印泥红浅底 */
    sealSoft: '#FDEBEC',
    /** 语义色（低饱和） */
    success: '#346538',
    warning: '#956400',
    info: '#1F6C9F',
  },
  font: {
    /**
     * 极简现代：全局单一无衬线（系统栈，中文 PingFang 优先）。
     * 展示层级靠字重与紧字距表达，不换字体家族。
     */
    body: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif',
    /** 品牌「记」字印章专用（logo 资产，非正文层级） */
    seal: '"Songti SC", "STSong", "Noto Serif SC", serif',
  },
  fontSize: {
    xs: '12px',
    sm: '13px',
    /** 正文基准（保持用户要求的大字号） */
    base: '15px',
    md: '16px',
    /** 名册姓名 */
    name: '17px',
    /** 页题 */
    display: '32px',
    hero: '44px',
  },
  radius: {
    /** 控件圆角（极简利落） */
    control: '6px',
    /** 卡片/浮层圆角（minimalist-ui 上限 12 内） */
    float: '10px',
  },
  shadow: {
    /** 唯一允许的阴影：行/卡片悬停的极轻浮起 */
    hover: '0 2px 8px rgba(0, 0, 0, 0.04)',
  },
  motion: {
    /** 常规过渡（极简标准缓出） */
    ease: '200ms cubic-bezier(0.16, 1, 0.3, 1)',
    /** 内容进入 */
    entry: '600ms cubic-bezier(0.16, 1, 0.3, 1)',
  },
  layout: {
    sidebarWidth: '208px',
    contentMaxWidth: '1080px',
  },
} as const

export type DesignTokens = typeof tokens
