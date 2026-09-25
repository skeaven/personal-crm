<script setup lang="ts">
/** 图谱页：graphGL 力导向关系图（全图/中心 N 度展开），节点点击出信息卡，可切换中心。 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { graphApi } from '@/api/graph'
import { ApiError } from '@/api/client'
import type { GraphDataOut, RelationshipOut } from '@/api/types'
import { useContactOptions } from '@/composables/useContactOptions'
import ContactAvatar from '@/components/ContactAvatar.vue'
import RelationGraphGL from '@/components/RelationGraphGL.vue'

const router = useRouter()
const { options, load: loadContacts } = useContactOptions()

const loading = ref(false)
const centerId = ref<number | null>(null)
const depth = ref<number>(2)
const graphData = ref<GraphDataOut>({ nodes: [], links: [] })

// 选中节点的信息卡状态
const selected = ref<{
  id: number
  name: string
  tier: string
  kinship: string | null
  relations: RelationshipOut[]
} | null>(null)

/** 拉取图数据并刷新画布（组件内部做全量替换渲染）。 */
async function loadGraph(): Promise<void> {
  loading.value = true
  try {
    graphData.value = await graphApi.graphData({
      center_id: centerId.value ?? undefined,
      depth: depth.value,
    })
    selected.value = null
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('图谱加载失败')
  } finally {
    loading.value = false
  }
}

/** 画布点击节点：侧栏展示称谓（D15 从"我"推导）+ 关系列表。 */
async function showNodeInfo(contactId: number): Promise<void> {
  const node = graphData.value.nodes.find((item) => item.id === contactId)
  if (!node) return
  try {
    const [relations, kinship] = await Promise.all([
      graphApi.relationships(contactId),
      graphApi.kinship(contactId).catch(() => null), // 未绑定"我"时不阻断信息卡
    ])
    selected.value = {
      id: node.id,
      name: node.name,
      tier: node.tier,
      kinship: kinship?.found ? (kinship.title ?? null) : null,
      relations,
    }
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '关系加载失败')
  }
}

/** 以某人为中心重看图谱。 */
function focusOn(contactId: number): void {
  centerId.value = contactId
  void loadGraph()
}

/** 清除中心，回到全图。 */
function resetCenter(): void {
  centerId.value = null
  void loadGraph()
}

onMounted(async () => {
  await Promise.all([loadContacts(), loadGraph()])
})
</script>

<template>
  <div class="crm-page crm-page--full graph-page">
    <header class="crm-page-head">
      <div>
        <h1 class="crm-page-title crm-display">关系图谱</h1>
        <p class="crm-page-sub">
          共 {{ graphData.nodes.length }} 人 · {{ graphData.links.length }} 条关系
        </p>
      </div>
      <div class="controls">
        <el-select
          v-model="centerId"
          filterable
          clearable
          placeholder="以谁为中心"
          class="center-select"
          @change="loadGraph"
        >
          <el-option
            v-for="opt in options"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-radio-group v-model="depth" @change="loadGraph">
          <el-radio-button :value="1">一度</el-radio-button>
          <el-radio-button :value="2">二度</el-radio-button>
          <el-radio-button :value="3">三度</el-radio-button>
        </el-radio-group>
      </div>
    </header>

    <div v-loading="loading" class="graph-layout">
      <div class="canvas-card">
        <RelationGraphGL :data="graphData" @node-click="showNodeInfo" />
        <el-button v-if="centerId" text class="reset-btn" @click="resetCenter">
          查看全图
        </el-button>
        <el-empty v-if="!loading && !graphData.nodes.length" description="还没有联系人" class="canvas-empty" />
      </div>

      <aside v-if="selected" class="info-card crm-rise">
        <div class="info-head">
          <ContactAvatar :name="selected.name" :size="44" />
          <div>
            <div class="info-name">
              {{ selected.name }}
              <el-tag v-if="selected.kinship" size="small" class="kinship-tag">{{ selected.kinship }}</el-tag>
            </div>
            <div class="info-meta">{{ selected.tier === 'direct' ? '直接联系人' : '边缘联系人' }}</div>
          </div>
        </div>
        <div class="info-relations">
          <div v-for="relation in selected.relations" :key="relation.id" class="relation-line">
            <span class="relation-label">{{ relation.type_label }}</span>
            <span class="relation-other">{{ relation.other_contact_name }}</span>
          </div>
          <div v-if="!selected.relations.length" class="relation-empty">暂无关系</div>
        </div>
        <div class="info-actions">
          <el-button @click="focusOn(selected.id)">以此为中心</el-button>
          <el-button type="primary" @click="router.push(`/contacts/${selected.id}`)">
            查看详情
          </el-button>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.controls {
  display: flex;
  gap: 10px;
  align-items: center;
}
.center-select {
  width: 200px;
}
.graph-layout {
  display: flex;
  gap: 14px;
  align-items: stretch;
}
.canvas-card {
  flex: 1;
  min-width: 0;
  position: relative;
  height: 640px;
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
}
.reset-btn {
  position: absolute;
  top: 10px;
  right: 12px;
}
.canvas-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.info-card {
  width: 260px;
  flex-shrink: 0;
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.info-head {
  display: flex;
  gap: 12px;
  align-items: center;
}
.info-name {
  font-size: 17px;
  font-weight: 600;
}
.kinship-tag {
  margin-left: 6px;
}
.info-meta {
  color: var(--crm-muted);
  font-size: 13px;
  margin-top: 2px;
}
.info-relations {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.relation-line {
  display: flex;
  gap: 8px;
  font-size: 14px;
}
.relation-label {
  color: var(--crm-seal);
  min-width: 48px;
}
.relation-other {
  color: var(--crm-ink);
}
.relation-empty {
  color: var(--crm-muted);
  font-size: 13px;
}
.info-actions {
  display: flex;
  gap: 8px;
  margin-top: auto;
}
@media (max-width: 720px) {
  .graph-layout {
    flex-direction: column;
  }
  .canvas-card {
    height: 420px;
  }
  .info-card {
    width: auto;
  }
}
</style>
