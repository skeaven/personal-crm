<script setup lang="ts">
/** 关系图容器：echarts-gl graphGL（WebGL 力导向）的 Vue 封装（D13）。
 * 只负责渲染生命周期（init / resize / 数据更新 / dispose），数据进、事件出：
 * 节点点击以 node-click(contactId) 抛给父组件处理业务（跳转/信息卡）。
 * 视觉（墨/灰双层 + 印泥红强调）只消费 design tokens（chartPalette）。 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import 'echarts-gl'
import { chartPalette } from '@/design/theme'
import type { GraphDataOut } from '@/api/types'

const props = defineProps<{
  /** 图数据（nodes/links），来自 graph 模块 GET /graph/data。 */
  data: GraphDataOut
}>()

const emit = defineEmits<{
  (e: 'node-click', contactId: number): void
}>()

const host = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null

/** 组装 graphGL option：graphGL 系列不在 echarts 官方类型内，整体做一次显式收窄。 */
function buildOption(): echarts.EChartsOption {
  const palette = chartPalette
  const option = {
    tooltip: {
      /* 悬停节点显示名字与层级；边上无 data.tier 自然不触发分支 */
      formatter: (params: unknown) => {
        const data = (params as { data?: { name?: string; tier?: string } }).data
        if (!data?.tier) return ''
        const tierLabel = data.tier === 'direct' ? '直接联系人' : '边缘联系人'
        return `${data.name} · ${tierLabel}`
      },
    },
    series: [
      {
        type: 'graphGL',
        nodes: props.data.nodes.map((node) => ({
          id: String(node.id),
          name: node.name,
          tier: node.tier,
          symbolSize: node.tier === 'direct' ? 20 : 11,
          itemStyle: {
            color: node.tier === 'direct' ? palette.ink : palette.muted,
            opacity: node.tier === 'direct' ? 1 : 0.5,
          },
        })),
        edges: props.data.links.map((link) => ({
          source: String(link.source),
          target: String(link.target),
        })),
        // 家庭量级（<百节点）用 CPU 布局：确定性更好，规避 GPU 浮点纹理兼容问题；
        // linLog 对稀疏小图分离最好；gravityCenter 锚定视口原点，保证初始视图居中
        forceAtlas2: {
          GPU: false,
          steps: 5,
          maxSteps: 600,
          linLogMode: true,
          gravity: 1,
          scaling: 5,
          preventOverlap: true,
          edgeWeightInfluence: 0,
          gravityCenter: [0, 0],
        },
        roam: true, // 拖拽平移 + 滚轮缩放
        label: {
          show: true,
          formatter: '{b}',
          position: 'right',
          distance: 6,
          color: palette.ink,
          fontSize: 12,
          // graphGL 源自 echarts4 期实现，textStyle 兼容通道一并配置
          textStyle: { color: palette.ink, fontSize: 12 },
        },
        lineStyle: { color: palette.line, width: 1, opacity: 0.9 },
        emphasis: {
          itemStyle: { color: palette.seal, opacity: 1 },
          label: { show: true },
        },
      },
    ],
  }
  return option as unknown as echarts.EChartsOption
}

/** 点击节点向外抛业务 id；边的点击负载无 tier，天然被过滤。 */
function handleClick(params: unknown): void {
  const data = (params as { data?: { tier?: string; id?: string } }).data
  if (data?.tier && data.id) emit('node-click', Number(data.id))
}

onMounted(() => {
  if (!host.value) return
  chart = echarts.init(host.value)
  chart.setOption(buildOption())
  chart.on('click', handleClick)
  // 容器随布局变化时同步画布（主页栅格折叠/窗口缩放）
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(host.value)
})

watch(
  () => props.data,
  () => {
    // notMerge：节点/边可能减少，全量替换避免残影
    chart?.setOption(buildOption(), { notMerge: true })
  },
  { deep: true },
)

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="host" class="graph-gl-host" />
</template>

<style scoped>
.graph-gl-host {
  width: 100%;
  height: 100%;
  min-height: 240px;
}
</style>
