/**
 * 主题装配（D13）：Element Plus 换肤收敛于 design/element-plus.css 的 CSS 变量映射层；
 * 本文件只保留品牌资产与 ECharts 共享色板（图配色同样只消费 tokens）。
 */
import { tokens } from './tokens'

/** 印章 logo 属性：登录页与侧边栏共用的品牌元素（印泥红方块「记」字，唯一彩色瞬间） */
export const sealBrand = {
  text: '记',
  background: tokens.color.seal,
  color: '#FFFFFF',
  fontFamily: tokens.font.seal,
}

/** ECharts / echarts-gl 共享色板：纸墨风格（墨黑主线 + 印泥红唯一彩色瞬间）。 */
export const chartPalette = {
  ink: tokens.color.ink,
  inkHover: tokens.color.inkHover,
  /** ink 30% 派生档（与 element-plus.css 的 light-7 同源）：choropleth 渐变中间色 */
  inkSoft: '#BFBFBF',
  muted: tokens.color.muted,
  line: tokens.color.line,
  bone: tokens.color.bone,
  canvas: tokens.color.canvas,
  seal: tokens.color.seal,
} as const
