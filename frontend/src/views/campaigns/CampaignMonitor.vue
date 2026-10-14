<template>
  <div>
    <PageHeader
      title="营销计划"
      description="人群 × 内容 × 通道 批量触达：预估确认后启动；实时进度、暂停/恢复/中止，全程台账可查。"
    >
      <template #actions>
        <el-button type="primary" @click="wizardRef?.open()">新建计划</el-button>
        <el-button @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <OnboardingHint
      v-if="!loading && !items.length"
      storage-key="onboarding.campaigns"
      title="第一次做批量触达？4 步走通"
      :steps="[
        '创建计划：圈人群（默认排除已回复/已成交与退订对象）',
        '选择「已发布」内容与语言策略，选择发送通道',
        '先试发 2 封给自己/同事，确认效果后点「启动」',
        '在台账页跟踪每条去向；失败可重试，中途可暂停',
      ]"
      hint="提示：没有可发客户？先到「客户列表」完成挖掘与导入。"
    />

    <el-card shadow="never">
      <el-table v-loading="loading" :data="items" highlight-current-row @current-change="selectRow">
        <el-table-column prop="name" label="计划" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="进度" width="220">
          <template #default="{ row }">
            <template v-if="row.stats && row.stats.planned">
              <el-progress
                :percentage="progressOf(row as CampaignRow)"
                :status="row.status === 'completed' ? 'success' : undefined"
              />
              <span class="muted">已发 {{ row.stats.sent ?? 0 }} / {{ row.stats.planned }}</span>
            </template>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="失败/退信" width="100">
          <template #default="{ row }">
            <span :class="{ warn: (row.stats?.failed ?? 0) + (row.stats?.bounced ?? 0) > 0 }">
              {{ (row.stats?.failed ?? 0) + (row.stats?.bounced ?? 0) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ (row.created_at || '').slice(0, 19).replace('T', ' ') }}</template>
        </el-table-column>
        <el-table-column label="操作" width="330" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="['draft', 'running'].includes(row.status)"
              size="small" text type="primary" :loading="busyId === row.id"
              @click="start(row as CampaignRow)"
            >
              启动
            </el-button>
            <el-button
              v-if="row.status === 'running'"
              size="small" text type="warning"
              @click="control(row as CampaignRow, 'pause')"
            >
              暂停
            </el-button>
            <el-button
              v-if="row.status === 'paused'"
              size="small" text type="success"
              @click="control(row as CampaignRow, 'resume')"
            >
              恢复
            </el-button>
            <el-button
              v-if="['running', 'paused'].includes(row.status)"
              size="small" text type="danger"
              @click="control(row as CampaignRow, 'cancel')"
            >
              中止
            </el-button>
            <el-button size="small" text @click="goRecords(row as CampaignRow)">台账</el-button>
            <el-button size="small" text @click="goReport(row as CampaignRow)">报表</el-button>
            <el-button
              v-if="['draft', 'completed', 'cancelled'].includes(row.status)"
              size="small" text type="danger"
              @click="remove(row as CampaignRow)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="selected" shadow="never" class="monitor">
      <template #header>
        <div class="head">
          <span>实时监控 · {{ selected.name }}</span>
          <div>
            <el-button size="small" :loading="testSending" @click="testSend">试发 2 封</el-button>
            <el-button size="small" @click="refreshSelected">刷新</el-button>
          </div>
        </div>
      </template>

      <el-descriptions :column="4" border>
        <el-descriptions-item label="状态"><StatusTag :status="selected.status" /></el-descriptions-item>
        <el-descriptions-item label="通道">
          {{ (selected.channels || []).map((c) => `${c.name}(${c.role === 'primary' ? '主' : '备'})`).join('、') || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="轮次">
          {{ (selected.rounds || []).map((r) => `R${r.round_no}·${r.status}`).join(' ') || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="统计">
          已发 {{ selected.stats?.sent ?? 0 }} / 计划 {{ selected.stats?.planned ?? 0 }}
        </el-descriptions-item>
      </el-descriptions>

      <div v-if="live" class="live">
        <el-progress
          :percentage="livePercentage"
          :status="liveDone ? 'success' : undefined"
          :stroke-width="16"
          text-inside
        />
        <div class="muted">
          已发 {{ live.sent ?? 0 }} · 失败 {{ live.failed ?? 0 }} · 退信 {{ live.bounced ?? 0 }} ·
          跳过 {{ live.skipped ?? 0 }} · 排除 {{ live.suppressed ?? 0 }} · 剩余 {{ live.remaining ?? 0 }}
        </div>
      </div>

      <div v-if="logs.length" class="logs">
        <div v-for="(line, index) in logs.slice(-8)" :key="index" class="log-line">{{ line }}</div>
      </div>

      <el-alert
        v-if="selected.status === 'running'"
        class="mb"
        type="info"
        :closable="false"
        show-icon
        title="发送进行中：可随时暂停/恢复/中止；中断的计划保留未发记录，重新启动即断点续发。"
      />
    </el-card>

    <CampaignWizard ref="wizardRef" @done="load" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../../api/client'
import { TERMINAL_STATUSES } from '../../api/jobs'
import { useJobCenterStore } from '../../stores/jobCenter'
import type { CampaignRow } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import OnboardingHint from '../../components/common/OnboardingHint.vue'
import CampaignWizard from './CampaignWizard.vue'

const router = useRouter()
const items = ref<CampaignRow[]>([])
const loading = ref(false)
const busyId = ref<number | null>(null)
const testSending = ref(false)
const selected = ref<CampaignRow | null>(null)
const wizardRef = ref<InstanceType<typeof CampaignWizard> | null>(null)

// 实时监控一律读全局任务中心 store（同源一致 FR-008；进入页面自动选中活跃发送）
const store = useJobCenterStore()

const campaignJob = computed(() => {
  const jobId = selected.value?.active_job_id
  if (jobId == null) return null
  return store.activeJobs[jobId] ?? store.recentJobs.find((job) => job.id === jobId) ?? null
})

const live = computed<Record<string, number> | null>(() => {
  const job = campaignJob.value
  if (!job) return null
  const entries = Object.entries(job.progress ?? {}).filter(([, value]) => typeof value === 'number')
  if (!entries.length && !TERMINAL_STATUSES.includes(job.status)) return null
  return Object.fromEntries(entries) as Record<string, number>
})
const liveDone = computed(
  () => !!campaignJob.value && TERMINAL_STATUSES.includes(campaignJob.value.status),
)
const logs = computed(() => {
  const id = campaignJob.value?.id
  if (id === undefined) return []
  return (store.logs[id] ?? []).map((line) => line.message)
})

const livePercentage = computed(() => {
  if (!live.value) return 0
  const total = live.value.total || 0
  if (!total) return liveDone.value ? 100 : 0
  const done = (live.value.sent || 0) + (live.value.failed || 0) + (live.value.bounced || 0)
    + (live.value.skipped || 0) + (live.value.suppressed || 0)
  return Math.min(Math.round((done / total) * 100), 100)
})

function progressOf(row: CampaignRow): number {
  const stats = row.stats || {}
  const planned = stats.planned || 0
  if (!planned) return 0
  return Math.min(Math.round(((stats.sent || 0) / planned) * 100), 100)
}

async function load() {
  loading.value = true
  try {
    items.value = await api.get<CampaignRow[]>('/campaigns')
    if (selected.value) {
      const current = items.value.find((item) => item.id === selected.value?.id)
      if (current) selected.value = current
    }
    autoSelect()
  } finally {
    loading.value = false
  }
}

/** 进入页面自动选中活跃发送计划（store.init 可能晚于本页挂载，watch 兜底补选） */
function autoSelect() {
  if (selected.value) return
  const job = store.activeJobOfType('campaign_send')
  if (!job || job.ref_type !== 'campaign' || job.ref_id == null) return
  const row = items.value.find((item) => item.id === job.ref_id)
  if (row) void selectRow(row)
}
watch(() => store.activeList, autoSelect)

async function selectRow(row: CampaignRow | null) {
  if (!row) return
  selected.value = await api.get<CampaignRow>(`/campaigns/${row.id}`)
  attachJob()
}

/** 确保 store 正在跟踪该计划的任务（未跟踪则 register 自愈：拉详情 + 订阅） */
function attachJob() {
  const jobId = selected.value?.active_job_id
  if (jobId != null && !store.activeJobs[jobId]) void store.register(jobId)
}

// store 中任务到达终态 → 刷新计划详情与列表（取代旧 onDone 回调）
watch(
  () => campaignJob.value?.status,
  async (status) => {
    if (status && TERMINAL_STATUSES.includes(status)) {
      await refreshSelected()
      await load()
    }
  },
)

async function refreshSelected() {
  if (!selected.value) return
  selected.value = await api.get<CampaignRow>(`/campaigns/${selected.value.id}`)
}

async function start(row: CampaignRow) {
  busyId.value = row.id
  try {
    const pendingRound = (row.rounds || []).find((round) => round.status === 'pending')
    const roundNo = pendingRound?.round_no ?? 1
    await api.post<{ job_id: number }>(`/campaigns/${row.id}/rounds/${roundNo}/start`)
    ElMessage.success(`第 ${roundNo} 轮已启动（进度可在任务中心随时查看）`)
    selected.value = row
    await selectRow(row)
    await load()
  } finally {
    busyId.value = null
  }
}

async function control(row: CampaignRow, action: 'pause' | 'resume' | 'cancel') {
  if (action === 'cancel') {
    try {
      await ElMessageBox.confirm('中止后未发送记录将不再执行（保留在台账）。确认中止？', '中止计划', {
        type: 'warning', confirmButtonText: '中止', cancelButtonText: '取消',
      })
    } catch {
      return
    }
  }
  await api.post(`/campaigns/${row.id}/${action}`)
  ElMessage.success({ pause: '已暂停', resume: '已恢复', cancel: '已中止' }[action])
  await refreshSelected()
  // 控制经 /campaigns 端点（带外）：同步 store 中该任务的状态（FR-008 两处一致）
  const jobId = selected.value?.active_job_id
  if (jobId != null) await store.refresh(jobId)
  await load()
}

async function testSend() {
  if (!selected.value) return
  testSending.value = true
  try {
    const result = await api.post<{ sent: number; to: string }>(
      `/campaigns/${selected.value.id}/test-send`,
      { n: 2, to_self: true },
    )
    ElMessage.success(`已试发 ${result.sent} 封到 ${result.to}（不占计划额度）`)
  } finally {
    testSending.value = false
  }
}

function goRecords(row: CampaignRow) {
  router.push(`/campaigns/${row.id}/records`)
}
function goReport(row: CampaignRow) {
  router.push(`/campaigns/${row.id}/report`)
}

async function remove(row: CampaignRow) {
  try {
    await ElMessageBox.confirm(`删除计划「${row.name}」及其台账？此操作不可恢复。`, '删除计划', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await api.del(`/campaigns/${row.id}`)
  if (selected.value?.id === row.id) selected.value = null
  ElMessage.success('已删除')
  await load()
}

onMounted(load)
</script>

<style scoped>
.monitor {
  margin-top: 12px;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.live {
  margin: 14px 0 6px;
}
.live .muted {
  margin-top: 6px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.warn {
  color: var(--el-color-danger);
}
.logs {
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 8px 12px;
  margin: 10px 0;
  font-size: 12px;
  max-height: 160px;
  overflow: auto;
}
.log-line {
  line-height: 1.7;
  color: var(--el-text-color-regular);
}
.mb {
  margin-top: 8px;
}
</style>
