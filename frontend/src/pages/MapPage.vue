<script setup lang="ts">
/** 地图页：联系人地理分布（geo choropleth 省份计数着色 + 散点撒人），点击散点跳详情。
 * 地图数据 = DataV.GeoAtlas 开放数据 vendor（assets/geo/china.json），不运行时拉取。
 * 配色只消费 chartPalette（骨灰白 → 墨黑渐变，印泥红不参与着色）。 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { contactsApi } from '@/api/contacts'
import { ApiError } from '@/api/client'
import { chartPalette } from '@/design/theme'
import chinaGeo from '@/assets/geo/china.json'
import type { MapPointsOut } from '@/api/types'

const router = useRouter()

const loading = ref(false)
const mapData = ref<MapPointsOut>({ points: [], provinces: [] })

const host = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null

/** 已标记位置的人数与覆盖省份数（页头摘要）。 */
const summary = computed(
  () => `${mapData.value.points.length} 位联系人已标记所在地 · 覆盖 ${mapData.value.provinces.length} 个省级地区`,
)

/** 组装 choropleth + scatter option（类型：geo/map 系列在 echarts 类型内，无需断言）。 */
function buildOption(): echarts.EChartsOption {
  const palette = chartPalette
  const maxCount = Math.max(1, ...mapData.value.provinces.map((p) => p.count))
  return {
    tooltip: {
      trigger: 'item',
      backgroundColor: palette.canvas,
      borderColor: palette.line,
      textStyle: { color: palette.ink, fontSize: 13 },
      formatter: (params) => {
        const name = (params as { name?: string }).name ?? ''
        if ((params as { seriesType?: string }).seriesType === 'map') {
          const count = (params as { value?: number }).value ?? 0
          return count > 0 ? `${name} · ${count} 人` : name
        }
        return name
      },
    },
    visualMap: {
      type: 'continuous',
      min: 0,
      max: maxCount,
      seriesIndex: 0,
      show: false, // v3 风格：着色梯度自明，不放图例滑块
      inRange: { color: [palette.bone, palette.inkSoft, palette.muted, palette.ink] },
    },
    geo: {
      map: 'china',
      roam: true,
      zoom: 1.15,
      itemStyle: { areaColor: palette.bone, borderColor: palette.canvas },
      emphasis: {
        label: { show: false },
        itemStyle: { areaColor: palette.inkSoft },
      },
      selectedMode: false,
    },
    series: [
      {
        type: 'map',
        map: 'china',
        geoIndex: 0,
        data: mapData.value.provinces.map((province) => ({
          name: province.name,
          value: province.count,
        })),
      },
      {
        type: 'scatter',
        coordinateSystem: 'geo',
        data: mapData.value.points.map((point) => ({
          name: point.display_name,
          value: [point.lng, point.lat],
          contactId: point.contact_id,
          tier: point.tier,
          symbolSize: point.tier === 'direct' ? 12 : 7,
          itemStyle: {
            color: palette.ink,
            opacity: point.tier === 'direct' ? 1 : 0.45,
            borderColor: palette.canvas,
            borderWidth: 1,
          },
        })),
        emphasis: {
          scale: 1.6,
          itemStyle: { color: palette.seal, opacity: 1 },
        },
      },
    ],
  }
}

/** 散点点击跳联系人详情；省份块点击不响应。 */
function handleChartClick(params: unknown): void {
  const data = (params as { data?: { contactId?: number } }).data
  if (data?.contactId) router.push(`/contacts/${data.contactId}`)
}

/** 拉取地图数据并渲染（家庭量级一次全量）。 */
async function loadMap(): Promise<void> {
  loading.value = true
  try {
    mapData.value = await contactsApi.mapPoints()
    chart?.setOption(buildOption(), { notMerge: true })
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('地图数据加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  echarts.registerMap('china', chinaGeo as Parameters<typeof echarts.registerMap>[1])
  if (!host.value) return
  chart = echarts.init(host.value)
  chart.on('click', handleChartClick)
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(host.value)
  void loadMap()
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div class="crm-page map-page">
    <header class="crm-page-head">
      <div>
        <h1 class="crm-page-title crm-display">地 图</h1>
        <p class="crm-page-sub">{{ summary }}</p>
      </div>
      <p class="map-hint">在联系人编辑里填写"所在地"即可上图</p>
    </header>

    <div v-loading="loading" class="map-card">
      <div ref="host" class="map-host" />
      <el-empty
        v-if="!loading && !mapData.points.length"
        description="还没有人标记位置，去联系人编辑里填一个「所在地」"
        class="map-empty"
      />
    </div>
  </div>
</template>

<style scoped>
.map-page {
  max-width: none;
}
.map-hint {
  margin: 0;
  color: var(--crm-muted);
  font-size: 13px;
}
.map-card {
  position: relative;
  height: 680px;
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
}
.map-host {
  width: 100%;
  height: 100%;
}
.map-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
@media (max-width: 720px) {
  .map-card {
    height: 460px;
  }
}
</style>
