<template>
  <div>
    <PageHeader
      title="检索渠道"
      description="配置搜索引擎接入（用户自备密钥）。按优先级自动故障转移：命中限流/封禁时切换下一渠道。"
    >
      <template #actions>
        <el-button type="primary" @click="openCreate">添加渠道</el-button>
        <el-button @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="items">
        <el-table-column prop="name" label="名称" min-width="180" />
        <el-table-column label="类型" width="130">
          <template #default="{ row }">{{ presets[row.type_key]?.display || row.type_key }}</template>
        </el-table-column>
        <el-table-column label="优先级" width="80">
          <template #default="{ row }">{{ row.priority }}</template>
        </el-table-column>
        <el-table-column label="启用" width="70">
          <template #default="{ row }">
            <el-switch
              :model-value="row.enabled"
              @change="(value: string | number | boolean) => toggleEnabled(row as SearchProviderRow, Boolean(value))"
            />
          </template>
        </el-table-column>
        <el-table-column label="健康" width="86">
          <template #default="{ row }">
            <el-tag :type="healthType(row.health)" size="small">{{ healthLabel(row.health) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="今日用量" width="90">
          <template #default="{ row }">{{ row.used_today }}</template>
        </el-table-column>
        <el-table-column label="最近测试" width="150">
          <template #default="{ row }">
            {{ row.last_test_at ? row.last_test_at.slice(0, 19).replace('T', ' ') : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" :loading="testingId === row.id" @click="test(row as SearchProviderRow)">测试</el-button>
            <el-button size="small" text @click="openEdit(row as SearchProviderRow)">编辑</el-button>
            <el-button size="small" text type="danger" @click="remove(row as SearchProviderRow)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-alert v-if="lastDetail" class="detail" :type="lastOk ? 'success' : 'error'" :closable="false" :title="lastDetail" />
      <el-alert
        class="detail"
        type="info"
        :closable="false"
        show-icon
        title="建议顺序：Serper（注册最简）→ Brave → Tavily；DuckDuckGo 为非官方端点，仅作最后兜底。Bing 已退役、Google PSE 已对新客户关闭，均不可用。"
      />
    </el-card>

    <el-dialog v-model="formVisible" :title="editing ? '编辑渠道' : '添加渠道'" width="560px">
      <el-form label-width="110px">
        <el-form-item v-if="!editing" label="渠道类型">
          <el-select v-model="form.type_key" @change="applyPreset">
            <el-option v-for="(preset, key) in presets" :key="key" :value="key" :label="preset.display" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" required><el-input v-model="form.name" /></el-form-item>
        <el-form-item v-if="form.type_key !== 'ddg_html'" label="API 密钥">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            :placeholder="editing ? '留空则保持原密钥不变' : '粘贴服务商密钥'"
          />
        </el-form-item>
        <el-form-item label="端点">
          <el-input v-model="form.endpoint" placeholder="留空使用默认端点" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-input-number v-model="form.priority" :min="1" :max="999" />
          <span class="hint">数字小者先调用</span>
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
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
import type { SearchProviderRow } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'

interface Preset {
  display: string
  endpoint: string
  needs_key: boolean
  note: string
}

const items = ref<SearchProviderRow[]>([])
const presets = ref<Record<string, Preset>>({})
const loading = ref(false)
const testingId = ref<number | null>(null)
const lastDetail = ref('')
const lastOk = ref(false)
const formVisible = ref(false)
const editing = ref<SearchProviderRow | null>(null)
const form = ref({
  type_key: 'serper',
  name: '',
  api_key: '',
  endpoint: '',
  priority: 100,
  enabled: true,
})

function healthType(health: string): 'success' | 'danger' | 'info' {
  return health === 'healthy' ? 'success' : health === 'failing' ? 'danger' : 'info'
}

function healthLabel(health: string): string {
  return { healthy: '正常', failing: '异常', unknown: '未测' }[health] ?? health
}

async function load() {
  loading.value = true
  try {
    items.value = await api.get<SearchProviderRow[]>('/search/providers')
  } finally {
    loading.value = false
  }
}

async function loadPresets() {
  const body = await api.get<{ presets: Record<string, Preset> }>('/search/presets')
  presets.value = body.presets
}

function applyPreset() {
  const preset = presets.value[form.value.type_key]
  if (preset) {
    if (!form.value.name) form.value.name = preset.display
    form.value.endpoint = ''
  }
}

function openCreate() {
  editing.value = null
  form.value = {
    type_key: 'serper',
    name: '',
    api_key: '',
    endpoint: '',
    priority: 100,
    enabled: true,
  }
  applyPreset()
  formVisible.value = true
}

function openEdit(row: SearchProviderRow) {
  editing.value = row
  form.value = {
    type_key: row.type_key,
    name: row.name,
    api_key: '',
    endpoint: row.endpoint ?? '',
    priority: row.priority,
    enabled: row.enabled,
  }
  formVisible.value = true
}

async function submit() {
  if (!form.value.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  const payload: Record<string, unknown> = {
    name: form.value.name,
    endpoint: form.value.endpoint || null,
    priority: form.value.priority,
    enabled: form.value.enabled,
  }
  if (form.value.api_key) payload.api_key = form.value.api_key
  if (editing.value) {
    await api.put(`/search/providers/${editing.value.id}`, payload)
  } else {
    await api.post('/search/providers', { ...payload, type_key: form.value.type_key })
  }
  ElMessage.success('已保存')
  formVisible.value = false
  await load()
}

async function toggleEnabled(row: SearchProviderRow, value: boolean) {
  await api.put(`/search/providers/${row.id}`, { enabled: value })
  await load()
}

async function test(row: SearchProviderRow) {
  testingId.value = row.id
  lastDetail.value = ''
  try {
    const body = await api.post<{ ok: boolean; detail: string }>(`/search/providers/${row.id}/test`)
    lastOk.value = body.ok
    lastDetail.value = `${row.name}：${body.detail}`
  } finally {
    testingId.value = null
    await load()
  }
}

async function remove(row: SearchProviderRow) {
  await api.del(`/search/providers/${row.id}`)
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
