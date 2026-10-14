<template>
  <div>
    <PageHeader
      title="发送台账"
      :description="`计划 #${campaignId}：每位客户每轮收到哪一版内容、经哪个通道、何时发送、结果如何（FR-049）。`"
    >
      <template #actions>
        <el-button @click="router.push('/campaigns')">返回计划</el-button>
        <el-button @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <el-card shadow="never">
      <div class="filters">
        <el-select v-model="filters.status" clearable placeholder="状态" style="width: 140px" @change="reload">
          <el-option v-for="(label, key) in STATUS_LABELS" :key="key" :value="key" :label="label" />
        </el-select>
        <el-select v-model="filters.round_no" clearable placeholder="轮次" style="width: 120px" @change="reload">
          <el-option v-for="round in roundOptions" :key="round" :value="round" :label="`第 ${round} 轮`" />
        </el-select>
        <el-button
          type="warning"
          :disabled="!failedSelection.length"
          @click="retrySelected"
        >
          重试失败项（{{ failedSelection.length }}）
        </el-button>
        <span class="muted">失败/退信可勾选后重试；重试沿用同一台账记录（唯一键不变）</span>
      </div>

      <el-table
        v-loading="loading"
        :data="items"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="44" :selectable="(row: SendRecordRow) => ['failed', 'bounced'].includes(row.status)" />
        <el-table-column label="轮次" width="70">
          <template #default="{ row }">R{{ row.round_no }}</template>
        </el-table-column>
        <el-table-column prop="company_name" label="客户" min-width="160" show-overflow-tooltip />
        <el-table-column prop="contact_value" label="联系方式" min-width="170" show-overflow-tooltip />
        <el-table-column label="通道" width="130">
          <template #default="{ row }">{{ row.channel_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="语言" width="110">
          <template #default="{ row }">
            {{ langLabel(row.lang_used) }}
            <el-tag v-if="row.fallback_used" size="small" type="warning" class="chip">回退</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <StatusTag :status="row.status" />
            <el-tooltip v-if="row.skip_reason" :content="row.skip_reason" placement="top">
              <span class="muted">?</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="失败原因" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.error_code" class="error">{{ row.error_code }}：{{ row.error_message }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="发送时间" width="160">
          <template #default="{ row }">{{ row.sent_at ? row.sent_at.slice(0, 19).replace('T', ' ') : '—' }}</template>
        </el-table-column>
        <el-table-column label="内容版本" width="90">
          <template #default="{ row }">{{ row.content_version_id ? `#${row.content_version_id}` : '—' }}</template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="pager"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        @current-change="onPage"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import { useJobCenterStore } from '../../stores/jobCenter'
import type { Paginated, SendRecordRow } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import { langLabel } from '../../constants'

const STATUS_LABELS: Record<string, string> = {
  pending: '待发送',
  sent: '已发送',
  failed: '失败',
  bounced: '退信',
  skipped: '跳过',
  suppressed: '已排除',
}

const route = useRoute()
const router = useRouter()
const campaignId = Number(route.params.id)
const jobCenter = useJobCenterStore()

const items = ref<SendRecordRow[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = 50
const filters = ref({ status: '', round_no: undefined as number | undefined })
const failedSelection = ref<SendRecordRow[]>([])
const roundOptions = computed(() => {
  const rounds = new Set(items.value.map((row) => row.round_no))
  return [...rounds].sort((a, b) => a - b)
})

async function load() {
  loading.value = true
  try {
    const result = await api.get<Paginated<SendRecordRow>>(`/campaigns/${campaignId}/records`, {
      page: page.value,
      page_size: pageSize,
      status: filters.value.status || undefined,
      round_no: filters.value.round_no,
    })
    items.value = result.items
    total.value = result.total
  } finally {
    loading.value = false
  }
}

function reload() {
  page.value = 1
  failedSelection.value = []
  load()
}

function onPage(value: number) {
  page.value = value
  load()
}

function onSelectionChange(rows: SendRecordRow[]) {
  failedSelection.value = rows
}

async function retrySelected() {
  const ids = failedSelection.value.map((row) => row.id)
  const result = await api.post<{ reset: number; job_id: number | null }>(
    `/campaigns/${campaignId}/records/retry`,
    { record_ids: ids },
  )
  ElMessage.success(`已重置 ${result.reset} 条并重新发送`)
  if (result.job_id) {
    const job = await jobCenter.waitFor(result.job_id)
    ElMessage.success(`重试完成：成功 ${job.result?.sent ?? 0}`)
  }
  failedSelection.value = []
  await load()
}

onMounted(load)
</script>

<style scoped>
.filters {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.error {
  color: var(--el-color-danger);
  font-size: 12px;
}
.chip {
  margin-left: 4px;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
