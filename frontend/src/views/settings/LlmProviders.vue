<template>
  <div>
    <PageHeader
      title="大模型服务"
      description="配置 API 密钥以启用 AI 能力（种子扩充/翻译/文案）。密钥本地加密存储，界面与日志一律脱敏。"
    >
      <template #actions>
        <el-button type="primary" @click="openCreate">添加服务</el-button>
        <el-button @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="items">
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="base_url" label="接入地址" min-width="250" show-overflow-tooltip />
        <el-table-column prop="model" label="模型" width="150">
          <template #default="{ row }">{{ row.model || '—' }}</template>
        </el-table-column>
        <el-table-column label="严格 JSON" width="90">
          <template #default="{ row }">{{ row.params?.supports_json_schema ? '是' : '否' }}</template>
        </el-table-column>
        <el-table-column label="默认" width="70">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="健康" width="86">
          <template #default="{ row }">
            <el-tag :type="healthType(row.health)" size="small">{{ healthLabel(row.health) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近测试" width="150">
          <template #default="{ row }">{{ row.last_test_at ? row.last_test_at.slice(0, 19).replace('T', ' ') : '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" :loading="testingId === row.id" @click="test(row as LlmRow)">测试</el-button>
            <el-button size="small" text @click="openEdit(row as LlmRow)">编辑</el-button>
            <el-button size="small" text type="danger" @click="remove(row as LlmRow)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-alert
        v-if="lastDetail"
        class="detail"
        :type="lastOk ? 'success' : 'error'"
        :closable="false"
        :title="lastDetail"
      />
    </el-card>

    <el-dialog v-model="formVisible" :title="editing ? '编辑服务' : '添加服务'" width="580px">
      <el-form label-width="120px">
        <el-form-item v-if="!editing" label="预设模板">
          <el-select v-model="presetKey" clearable placeholder="选择后自动填充接入地址" @change="applyPreset">
            <el-option v-for="(preset, key) in presets" :key="key" :value="key" :label="preset.display" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" required><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="接入地址" required>
          <el-input v-model="form.base_url" placeholder="https://api.deepseek.com" />
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="form.model" placeholder="模型 ID 以服务商 /models 为准，可测试后填写" />
        </el-form-item>
        <el-form-item label="API 密钥">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            :placeholder="editing ? '留空则保持原密钥不变' : 'sk-…'"
          />
        </el-form-item>
        <el-form-item label="严格 JSON 输出">
          <el-switch v-model="form.supports_json_schema" />
          <span class="hint">服务端支持 json_schema 时开启（如 Qwen / Kimi）</span>
        </el-form-item>
        <el-form-item label="设为默认"><el-switch v-model="form.is_default" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import PageHeader from '../../components/common/PageHeader.vue'

interface LlmRow {
  id: number
  name: string
  provider_type: string
  base_url: string
  model: string
  params: { supports_json_schema?: boolean }
  is_default: boolean
  health: 'unknown' | 'healthy' | 'failing'
  last_test_at: string | null
  last_test_result: string | null
}

interface Preset {
  display: string
  base_url: string
  supports_json_schema?: boolean
}

const items = ref<LlmRow[]>([])
const loading = ref(false)
const presets = ref<Record<string, Preset>>({})
const presetKey = ref<string>('')
const testingId = ref<number | null>(null)
const lastDetail = ref('')
const lastOk = ref(false)

const formVisible = ref(false)
const editing = ref<LlmRow | null>(null)
const form = ref({
  name: '',
  base_url: '',
  model: '',
  api_key: '',
  supports_json_schema: false,
  is_default: false,
})

function healthType(health: string): 'success' | 'danger' | 'info' {
  if (health === 'healthy') return 'success'
  if (health === 'failing') return 'danger'
  return 'info'
}

function healthLabel(health: string): string {
  return { healthy: '正常', failing: '异常', unknown: '未测' }[health] ?? health
}

async function load() {
  loading.value = true
  try {
    items.value = await api.get<LlmRow[]>('/llm/providers')
  } finally {
    loading.value = false
  }
}

async function loadPresets() {
  const body = await api.get<{ presets: Record<string, Preset> }>('/llm/presets')
  presets.value = body.presets
}

function applyPreset(key: string) {
  const preset = presets.value[key]
  if (!preset) return
  if (!form.value.name) form.value.name = preset.display
  form.value.base_url = preset.base_url
  form.value.supports_json_schema = Boolean(preset.supports_json_schema)
}

function openCreate() {
  editing.value = null
  presetKey.value = ''
  form.value = {
    name: '',
    base_url: '',
    model: '',
    api_key: '',
    supports_json_schema: false,
    is_default: false,
  }
  formVisible.value = true
}

function openEdit(row: LlmRow) {
  editing.value = row
  form.value = {
    name: row.name,
    base_url: row.base_url,
    model: row.model,
    api_key: '',
    supports_json_schema: Boolean(row.params?.supports_json_schema),
    is_default: row.is_default,
  }
  formVisible.value = true
}

async function submit() {
  if (!form.value.name.trim() || !form.value.base_url.trim()) {
    ElMessage.warning('请填写名称与接入地址')
    return
  }
  const params = { supports_json_schema: form.value.supports_json_schema }
  if (editing.value) {
    const payload: Record<string, unknown> = {
      name: form.value.name,
      base_url: form.value.base_url,
      model: form.value.model,
      params,
      is_default: form.value.is_default,
    }
    if (form.value.api_key) payload.api_key = form.value.api_key // 留空 = 保留原密钥
    await api.put(`/llm/providers/${editing.value.id}`, payload)
  } else {
    await api.post('/llm/providers', {
      name: form.value.name,
      provider_type: 'openai_compatible',
      base_url: form.value.base_url,
      model: form.value.model,
      api_key: form.value.api_key || null,
      params,
      is_default: form.value.is_default,
    })
  }
  ElMessage.success('已保存')
  formVisible.value = false
  await load()
}

async function test(row: LlmRow) {
  testingId.value = row.id
  lastDetail.value = ''
  try {
    const body = await api.post<{ ok: boolean; detail: string; models: string[] | null }>(
      `/llm/providers/${row.id}/test`,
    )
    lastOk.value = body.ok
    const models = body.models?.length ? `（可用模型 ${body.models.length} 个）` : ''
    lastDetail.value = `${body.detail}${models}`
  } finally {
    testingId.value = null
    await load()
  }
}

async function remove(row: LlmRow) {
  await api.del(`/llm/providers/${row.id}`)
  ElMessage.success('已删除')
  await load()
}

onMounted(async () => {
  await Promise.all([load(), loadPresets()])
})
</script>

<style scoped>
.detail {
  margin-top: 12px;
}
.hint {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
