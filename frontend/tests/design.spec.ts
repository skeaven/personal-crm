/** 设计系统测试：tokens 是全站视觉唯一来源，改值必须是有意为之且全局生效。 */
import { describe, expect, it } from 'vitest'
import { tokens } from '@/design/tokens'
import { chartPalette, sealBrand } from '@/design/theme'

describe('设计 tokens（v3 纸墨极简）', () => {
  it('画布为纯白、次级面为骨灰白（无暖米底）', () => {
    expect(tokens.color.canvas).toBe('#FFFFFF')
    expect(tokens.color.bone).toBe('#F7F7F5')
  })

  it('正文与主按钮为近黑墨色（禁纯黑）', () => {
    expect(tokens.color.ink).toBe('#1A1A1A')
  })

  it('印泥红是全站唯一彩色（降饱和）', () => {
    expect(tokens.color.seal).toBe('#B93C2B')
  })

  it('字号保持用户要求的大字号：正文 15、姓名 17、页题 32', () => {
    expect(tokens.fontSize.base).toBe('15px')
    expect(tokens.fontSize.name).toBe('17px')
    expect(tokens.fontSize.display).toBe('32px')
  })

  it('圆角利落：控件 6、浮层 10', () => {
    expect(tokens.radius.control).toBe('6px')
    expect(tokens.radius.float).toBe('10px')
  })

  it('动效为极简缓出（无弹簧回弹）', () => {
    expect(tokens.motion.ease).toContain('cubic-bezier(0.16, 1, 0.3, 1)')
    expect(Object.keys(tokens.motion).sort()).toEqual(['ease', 'entry'])
  })
})

describe('图表共享色板（D13：ECharts/echarts-gl 消费 tokens）', () => {
  it('图谱/地图主线为墨黑，底色为骨灰白，结构线极浅灰', () => {
    expect(chartPalette.ink).toBe(tokens.color.ink)
    expect(chartPalette.bone).toBe(tokens.color.bone)
    expect(chartPalette.line).toBe(tokens.color.line)
  })

  it('印泥红作为图表唯一强调色（悬停/危险语义）', () => {
    expect(chartPalette.seal).toBe(tokens.color.seal)
  })

  it('印章品牌元素来自 tokens（唯一彩色瞬间）', () => {
    expect(sealBrand.background).toBe(tokens.color.seal)
    expect(sealBrand.fontFamily).toBe(tokens.font.seal)
  })
})
