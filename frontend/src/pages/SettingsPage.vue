<script setup lang="ts">
/** 设置页：LLM 运行时配置（D6.2）——随时切换，保存后即生效；连接测试发真实请求。 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { embeddingsApi, settingsApi } from '@/api/ai'
import { contactsApi } from '@/api/contacts'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { AiLlmConfigIn } from '@/api/types'

const loading = ref(false)
const testing = ref(false)
const configured = ref(false)
const testResult = ref<{ ok: boolean; message: string } | null>(null)

const form = ref<AiLlmConfigIn>({
  base_url: '',
  api_key: '',
  model: '',
  temperature: 0.0,
})

async function loadConfig(): Promise<void> {
  try {
    const config = await settingsApi.aiConfig()
    configured.value = config.configured
    if (config.configured) {
      form.value.base_url = config.base_url ?? ''
      form.value.model = config.model ?? ''
      form.value.temperature = config.temperature ?? 0
      // api_key 只回显掩码：留空表示沿用已保存的值由后端处理（当前策略：重新输入）
      form.value.api_key = ''
    }
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('配置加载失败')
  }
}

async function save(): Promise<void> {
  loading.value = true
  try {
    await settingsApi.saveAiConfig(form.value)
    ElMessage.success('已保存，立即生效')
    configured.value = true
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    loading.value = false
  }
}

async function test(): Promise<void> {
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await settingsApi.testAi(form.value)
  } catch (error) {
    testResult.value = { ok: false, message: error instanceof ApiError ? error.message : '测试失败' }
  } finally {
    testing.value = false
  }
}

// ---- Embedding 配置（语义检索；维度固定 1024） ----
const embeddingLoading = ref(false)
const embeddingTesting = ref(false)
const embeddingConfigured = ref(false)
const rebuilding = ref(false)
const rebuildResult = ref<string | null>(null)
const embeddingForm = ref({ base_url: '', api_key: '', model: '' })

async function loadEmbedding(): Promise<void> {
  try {
    const config = await settingsApi.embeddingConfig()
    embeddingConfigured.value = config.configured
    if (config.configured) {
      embeddingForm.value.base_url = config.base_url ?? ''
      embeddingForm.value.model = config.model ?? ''
      embeddingForm.value.api_key = ''
    }
  } catch {
    embeddingConfigured.value = false
  }
}

async function saveEmbedding(): Promise<void> {
  embeddingLoading.value = true
  try {
    await settingsApi.saveEmbeddingConfig(embeddingForm.value)
    ElMessage.success('Embedding 已保存；请在保存 LLM 后点击「重建语义索引」')
    embeddingConfigured.value = true
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    embeddingLoading.value = false
  }
}

async function testEmbedding(): Promise<void> {
  embeddingTesting.value = true
  testResult.value = null
  try {
    const result = await settingsApi.testEmbedding(embeddingForm.value)
    ElMessage.info(result.message)
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '测试失败')
  } finally {
    embeddingTesting.value = false
  }
}

/** 重建语义索引：全量对账，秒级完成。 */
async function rebuild(): Promise<void> {
  rebuilding.value = true
  rebuildResult.value = null
  try {
    const summary = await embeddingsApi.rebuild()
    rebuildResult.value = `已向量化 ${summary.embedded} 条，跳过未变更 ${summary.skipped} 条，清理失效 ${summary.removed} 条`
    ElMessage.success('语义索引已更新')
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '重建失败')
  } finally {
    rebuilding.value = false
  }
}

// ---- 高德 key（地理编码，D14）：未配置时联系人坐标走内置静态表 ----
const amapLoading = ref(false)
const amapTesting = ref(false)
const amapConfigured = ref(false)
const amapMasked = ref('')
const amapKey = ref('')

/** 读取高德 key 配置（只回显掩码）。 */
async function loadAmap(): Promise<void> {
  try {
    const config = await settingsApi.amapConfig()
    if (config.configured) {
      amapConfigured.value = true
      amapMasked.value = config.api_key_masked
    }
  } catch {
    amapConfigured.value = false
  }
}

/** 保存高德 key（Web 服务类型）。 */
async function saveAmap(): Promise<void> {
  amapLoading.value = true
  try {
    await settingsApi.saveAmapConfig({ api_key: amapKey.value })
    ElMessage.success('高德 key 已保存；联系人所在地将优先用高德解析')
    amapConfigured.value = true
    amapKey.value = ''
    await loadAmap()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    amapLoading.value = false
  }
}

/** 测试高德 key：真实解析一次固定地址。 */
async function testAmap(): Promise<void> {
  amapTesting.value = true
  try {
    const result = await settingsApi.testAmap({ api_key: amapKey.value })
    ElMessage.info(result.message)
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '测试失败')
  } finally {
    amapTesting.value = false
  }
}

// ---- 绑定"我是谁"（D15）：关系图视角与称谓推导的起点 ----
const auth = useAuthStore()
const bindingSaving = ref(false)
const bindingContactId = ref<number | null>(auth.user?.contact_id ?? null)
const bindingOptions = ref<{ label: string; value: number }[]>([])

/** 载入联系人列表供选择，并同步账号当前的绑定。 */
async function loadBinding(): Promise<void> {
  try {
    const contacts = await contactsApi.list()
    bindingOptions.value = contacts
      .filter((item) => item.status === 'active')
      .map((item) => ({ label: item.display_name, value: item.id }))
    bindingContactId.value = auth.user?.contact_id ?? null
  } catch {
    bindingOptions.value = []
  }
}

/** 保存绑定；解绑传 null。 */
async function saveBinding(): Promise<void> {
  bindingSaving.value = true
  try {
    await auth.bindContact(bindingContactId.value)
    ElMessage.success(bindingContactId.value ? '已绑定，称谓推导将以这个联系人为"我"' : '已解绑')
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    bindingSaving.value = false
  }
}

onMounted(() => {
  void loadConfig()
  void loadEmbedding()
  void loadAmap()
  void loadBinding()
})
</script>

<template>
  <div class="crm-page">
    <header class="crm-page-head">
      <div>
        <h1 class="crm-page-title crm-display">设 置</h1>
        <p class="crm-page-sub">LLM 运行时配置，保存后立即生效，无需重启</p>
      </div>
    </header>

    <el-alert
      v-if="!configured"
      type="warning"
      title="尚未配置 LLM"
      :closable="false"
      class="hint"
    >
      AI 助手在配置完成前不可用，名册/活动/礼物等功能不受影响。
    </el-alert>

    <div class="form-card">
      <el-form label-position="top">
        <el-form-item label="API 地址（OpenAI 兼容端点）">
          <el-input v-model="form.base_url" placeholder="如 https://api.openai.com/v1 或自建网关" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            :placeholder="configured ? '留空则无法保存（密钥不回显，重配时重新输入）' : 'sk-...'"
          />
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="form.model" placeholder="如 gpt-4o / glm-4.7 / qwen-max" />
        </el-form-item>
        <el-form-item label="温度（越高越发散）">
          <el-slider v-model="form.temperature" :min="0" :max="2" :step="0.1" />
        </el-form-item>
        <div class="actions">
          <el-button :loading="testing" @click="test">测试连接</el-button>
          <el-button type="primary" :loading="loading" :disabled="!form.base_url || !form.api_key || !form.model" @click="save">
            保存
          </el-button>
        </div>
      </el-form>

      <el-alert
        v-if="testResult"
        :type="testResult.ok ? 'success' : 'danger'"
        :closable="false"
        class="hint"
        :show-icon="true"
      >
        {{ testResult.message }}
      </el-alert>
    </div>

    <header class="section-head">
      <h2 class="section-title crm-display">语义检索（Embedding）</h2>
      <p class="section-sub">让 AI 按"含义"搜索往来记录；维度固定 1024，换供应商无需重建表</p>
    </header>
    <div class="form-card">
      <el-form label-position="top">
        <el-form-item label="API 地址（OpenAI 兼容端点）">
          <el-input v-model="embeddingForm.base_url" placeholder="如 https://open.bigmodel.cn/api/paas/v4" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="embeddingForm.api_key"
            type="password"
            show-password
            :placeholder="embeddingConfigured ? '密钥不回显，重配时重新输入' : 'sk-...'"
          />
        </el-form-item>
        <el-form-item label="模型（输出维度须为 1024）">
          <el-input v-model="embeddingForm.model" placeholder="如 embedding-3（dims=1024）/ text-embedding-3-small / bge-m3" />
        </el-form-item>
        <div class="actions">
          <el-button :loading="rebuilding" text @click="rebuild">重建语义索引</el-button>
          <el-button :loading="embeddingTesting" @click="testEmbedding">测试连接</el-button>
          <el-button
            type="primary"
            :loading="embeddingLoading"
            :disabled="!embeddingForm.base_url || !embeddingForm.api_key || !embeddingForm.model"
            @click="saveEmbedding"
          >
            保存
          </el-button>
        </div>
      </el-form>
      <el-alert v-if="rebuildResult" type="success" :closable="false" class="hint" :show-icon="true">
        {{ rebuildResult }}
      </el-alert>
    </div>

    <header class="section-head">
      <h2 class="section-title crm-display">地图（高德）</h2>
      <p class="section-sub">联系人所在地解析坐标用；未配置时走内置静态市县坐标表（市区级精度）</p>
    </header>
    <div class="form-card">
      <el-form label-position="top">
        <el-form-item label="高德 Web 服务 API Key">
          <el-input
            v-model="amapKey"
            type="password"
            show-password
            :placeholder="amapConfigured ? `已配置（${amapMasked}），重配时重新输入` : '在高德开放平台创建「Web 服务」类型 key'"
          />
        </el-form-item>
        <div class="actions">
          <el-button :loading="amapTesting" :disabled="!amapKey" @click="testAmap">测试连接</el-button>
          <el-button type="primary" :loading="amapLoading" :disabled="!amapKey" @click="saveAmap">
            保存
          </el-button>
        </div>
      </el-form>
    </div>

    <header class="section-head">
      <h2 class="section-title crm-display">我是谁</h2>
      <p class="section-sub">把账号绑定到名册里的联系人，关系图谱与 AI 称谓推导以这个节点为"我"</p>
    </header>
    <div class="form-card">
      <el-form label-position="top">
        <el-form-item label="名册中的联系人">
          <el-select
            v-model="bindingContactId"
            filterable
            clearable
            placeholder="选择代表你自己的联系人"
            class="full-width"
          >
            <el-option
              v-for="opt in bindingOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <div class="actions">
          <el-button type="primary" :loading="bindingSaving" @click="saveBinding">保存</el-button>
        </div>
      </el-form>
    </div>
  </div>
</template>

<style scoped>
.form-card {
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
  padding: 22px 26px;
  max-width: 560px;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.full-width {
  width: 100%;
}
.hint {
  margin-bottom: 16px;
  max-width: 560px;
}
.section-head {
  margin: 36px 0 12px;
}
.section-title {
  margin: 0;
  font-size: 20px;
}
.section-sub {
  margin: 6px 0 0;
  color: var(--crm-muted);
  font-size: 13px;
}
</style>
