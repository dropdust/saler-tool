<template>
  <div>
    <PageHeader
      title="营销通道"
      description="登记自有发送通道（邮件 P0 / 短信）：连通测试、身份与限额、用量与健康一目了然；密钥只写不读回。"
    >
      <template #actions>
        <el-button type="primary" @click="openCreate">添加通道</el-button>
        <el-button @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="items">
        <el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip />
        <el-table-column label="类型" width="130">
          <template #default="{ row }">
            {{ row.channel_type === 'email' ? '邮件' : '短信' }}
            <span class="muted">· {{ providerLabel(row as ChannelRow) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发件身份" min-width="170">
          <template #default="{ row }">
            {{ (row as ChannelRow).identity?.from_addr || (row as ChannelRow).identity?.signature || '—' }}
          </template>
        </el-table-column>
        <el-table-column label="限额" width="120">
          <template #default="{ row }">
            {{ row.daily_limit === 0 ? '不限' : `${row.daily_limit}/日` }} · {{ row.rate_per_minute }}/分
          </template>
        </el-table-column>
        <el-table-column label="健康" width="86">
          <template #default="{ row }">
            <el-tag :type="healthType(row.health)" size="small">{{ healthLabel(row.health) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="今日用量" width="100">
          <template #default="{ row }">
            {{ row.used_today }}<span class="muted">/{{ row.daily_limit === 0 ? '∞' : row.daily_limit }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计" width="80">
          <template #default="{ row }">{{ row.total_sent }}</template>
        </el-table-column>
        <el-table-column label="启用" width="70">
          <template #default="{ row }">
            <el-switch
              :model-value="row.status === 'active'"
              @change="(value: string | number | boolean) => toggleStatus(row as ChannelRow, Boolean(value))"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" :loading="testingId === row.id" @click="test(row as ChannelRow)">测试</el-button>
            <el-button size="small" text @click="openUsage(row as ChannelRow)">用量</el-button>
            <el-button size="small" text type="success" @click="openTestSend(row as ChannelRow)">试发</el-button>
            <el-button size="small" text @click="openEdit(row as ChannelRow)">编辑</el-button>
            <el-button size="small" text type="danger" @click="remove(row as ChannelRow)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <EmptyState v-if="!loading && !items.length" description="尚无发送通道：添加邮箱通道后即可测试发送（S9）" />
      <el-alert v-if="lastDetail" class="detail" :type="lastOk ? 'success' : 'error'" :closable="false" :title="lastDetail" />
      <el-alert
        class="detail"
        type="info"
        :closable="false"
        show-icon
        title="提示：多数邮箱需使用「授权码」而非登录密码；建议首次配置后立即运行「测试」并「试发」一封给自己。"
      />
    </el-card>

    <ChannelForm ref="formRef" @saved="load" />

    <el-dialog v-model="usageVisible" :title="`用量与健康 · ${usageChannel?.name ?? ''}`" width="480px">
      <div v-if="usage">
        <div class="usage-line">
          <span>今日已发</span>
          <strong>{{ usage.used_today }}</strong>
          <span class="muted">剩余 {{ usage.remaining_today ?? '不限' }}</span>
        </div>
        <el-progress
          v-if="usage.daily_limit > 0"
          :percentage="Math.min(Math.round((usage.used_today / Math.max(usage.daily_limit, 1)) * 100), 100)"
          :status="usage.used_today >= usage.daily_limit ? 'exception' : undefined"
        />
        <el-descriptions :column="2" border class="usage-desc">
          <el-descriptions-item label="每日上限">{{ usage.daily_limit === 0 ? '不限' : usage.daily_limit }}</el-descriptions-item>
          <el-descriptions-item label="发送频率">{{ usage.rate_per_minute }} 条/分钟</el-descriptions-item>
          <el-descriptions-item label="并发数">{{ usage.concurrency }}</el-descriptions-item>
          <el-descriptions-item label="累计发送">{{ usage.total_sent }}</el-descriptions-item>
          <el-descriptions-item label="健康">
            <el-tag :type="healthType(usage.health)" size="small">{{ healthLabel(usage.health) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="最近检测">
            {{ usage.last_check_at ? usage.last_check_at.slice(0, 19).replace('T', ' ') : '—' }}
          </el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-if="usage.last_check_result"
          class="detail"
          :type="usage.health === 'failing' ? 'error' : 'info'"
          :closable="false"
          :title="usage.last_check_result"
        />
      </div>
    </el-dialog>

    <el-dialog v-model="testSendVisible" :title="`试发测试 · ${testSendChannel?.name ?? ''}`" width="480px">
      <el-form label-width="100px">
        <el-form-item :label="testSendChannel?.channel_type === 'email' ? '发送到' : '手机号'">
          <el-input
            v-model="testSendTo"
            :placeholder="testSendChannel?.channel_type === 'email' ? 'me@example.com' : '+8613800000000'"
          />
        </el-form-item>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="试发使用内置样例文案，用于验证通道是否可用；不消耗每日计划额度。"
        />
        <el-alert
          v-if="testSendResult"
          class="detail"
          :type="testSendResult.ok ? 'success' : 'error'"
          :closable="false"
          :title="testSendResult.ok ? `发送成功（${testSendResult.message_id}）` : testSendResult.detail"
        />
      </el-form>
      <template #footer>
        <el-button @click="testSendVisible = false">关闭</el-button>
        <el-button type="primary" :loading="testSending" @click="submitTestSend">发送测试</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../../api/client'
import type { ChannelManifest, ChannelRow, ChannelUsageRow } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import EmptyState from '../../components/common/EmptyState.vue'
import ChannelForm from './ChannelForm.vue'

const items = ref<ChannelRow[]>([])
const manifests = ref<ChannelManifest[]>([])
const loading = ref(false)
const testingId = ref<number | null>(null)
const lastDetail = ref('')
const lastOk = ref(false)
const formRef = ref<InstanceType<typeof ChannelForm> | null>(null)

const usageVisible = ref(false)
const usageChannel = ref<ChannelRow | null>(null)
const usage = ref<ChannelUsageRow | null>(null)

const testSendVisible = ref(false)
const testSendChannel = ref<ChannelRow | null>(null)
const testSendTo = ref('')
const testSending = ref(false)
const testSendResult = ref<{ ok: boolean; message_id?: string; detail?: string } | null>(null)

function healthType(health: string): 'success' | 'danger' | 'info' {
  return health === 'healthy' ? 'success' : health === 'failing' ? 'danger' : 'info'
}

function healthLabel(health: string): string {
  return { healthy: '正常', failing: '异常', unknown: '未测' }[health] ?? health
}

function providerLabel(row: ChannelRow): string {
  const typeKey = String(row.config?.provider || '')
  const manifest = manifests.value.find((item) => item.type_key === typeKey)
  return manifest?.display_name ?? typeKey ?? '—'
}

async function load() {
  loading.value = true
  try {
    items.value = await api.get<ChannelRow[]>('/channels')
  } finally {
    loading.value = false
  }
}

async function loadManifests() {
  manifests.value = await api.get<ChannelManifest[]>('/channels/providers')
}

function openCreate() {
  formRef.value?.open(null, manifests.value)
}

function openEdit(row: ChannelRow) {
  formRef.value?.open(row, manifests.value)
}

async function test(row: ChannelRow) {
  testingId.value = row.id
  lastDetail.value = ''
  try {
    const body = await api.post<{ ok: boolean; detail: string }>(`/channels/${row.id}/test`)
    lastOk.value = body.ok
    lastDetail.value = `${row.name}：${body.detail}`
  } finally {
    testingId.value = null
    await load()
  }
}

async function openUsage(row: ChannelRow) {
  usageChannel.value = row
  usage.value = await api.get<ChannelUsageRow>(`/channels/${row.id}/usage`)
  usageVisible.value = true
}

function openTestSend(row: ChannelRow) {
  testSendChannel.value = row
  testSendTo.value = ''
  testSendResult.value = null
  testSendVisible.value = true
}

async function submitTestSend() {
  if (!testSendChannel.value) return
  if (!testSendTo.value.trim()) {
    ElMessage.warning('请填写收件地址')
    return
  }
  testSending.value = true
  try {
    testSendResult.value = await api.post<{ ok: boolean; message_id?: string; detail?: string }>(
      `/channels/${testSendChannel.value.id}/test-send`,
      { to: testSendTo.value.trim() },
    )
    await load()
  } catch {
    /* 客户端已提示 */
  } finally {
    testSending.value = false
  }
}

async function toggleStatus(row: ChannelRow, active: boolean) {
  await api.put(`/channels/${row.id}`, { status: active ? 'active' : 'disabled' })
  ElMessage.success(active ? '已启用' : '已停用')
  await load()
}

async function remove(row: ChannelRow) {
  try {
    await ElMessageBox.confirm(`删除通道「${row.name}」？历史台账不受影响。`, '删除通道', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await api.del(`/channels/${row.id}`)
  ElMessage.success('已删除')
  await load()
}

onMounted(async () => {
  await Promise.all([load(), loadManifests()])
})
</script>

<style scoped>
.detail {
  margin-top: 12px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.usage-line {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
}
.usage-line strong {
  font-size: 20px;
}
.usage-desc {
  margin-top: 12px;
}
</style>
