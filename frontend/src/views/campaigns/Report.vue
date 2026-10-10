<template>
  <div v-loading="loading">
    <PageHeader
      title="计划报表"
      :description="report ? `${report.campaign.name}｜按通道 / 语言 / 轮次统计（FR-048/053）` : '加载中…'"
    >
      <template #actions>
        <el-button @click="router.push('/campaigns')">返回计划</el-button>
        <el-button type="primary" :loading="exporting" @click="exportReport">导出台账（XLSX）</el-button>
      </template>
    </PageHeader>

    <template v-if="report">
      <el-row :gutter="12" class="cards">
        <el-col v-for="(item, key) in totalsCards" :key="key" :span="4">
          <el-card shadow="never" class="stat">
            <div class="num">{{ item.value }}</div>
            <div class="label">{{ item.label }}</div>
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never" class="section">
        <template #header>按通道</template>
        <el-table :data="groups('by_channel')">
          <el-table-column prop="key" label="通道" min-width="160" />
          <el-table-column v-for="column in columns" :key="column.key" :label="column.label" width="100">
            <template #default="{ row }">{{ row[column.key] ?? 0 }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never" class="section">
        <template #header>按语言</template>
        <el-table :data="groups('by_lang')">
          <el-table-column label="语言" width="140">
            <template #default="{ row }">{{ row.key === '（未发送）' ? row.key : langLabel(row.key) }}</template>
          </el-table-column>
          <el-table-column v-for="column in columns" :key="column.key" :label="column.label" width="100">
            <template #default="{ row }">{{ row[column.key] ?? 0 }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never" class="section">
        <template #header>按轮次</template>
        <el-table :data="groups('by_round')">
          <el-table-column label="轮次" width="140">
            <template #default="{ row }">第 {{ row.key }} 轮</template>
          </el-table-column>
          <el-table-column v-for="column in columns" :key="column.key" :label="column.label" width="100">
            <template #default="{ row }">{{ row[column.key] ?? 0 }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="导出内容包含「统计」与「台账」两个 Sheet：逐条记录哪位客户、哪个通道、哪版内容、何时发送、结果如何。"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import type { CampaignReportRow } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import { langLabel } from '../../constants'

const route = useRoute()
const router = useRouter()
const campaignId = Number(route.params.id)

const report = ref<CampaignReportRow | null>(null)
const loading = ref(false)
const exporting = ref(false)

const columns = [
  { key: 'planned', label: '总记录' },
  { key: 'sent', label: '已发送' },
  { key: 'failed', label: '失败' },
  { key: 'bounced', label: '退信' },
  { key: 'skipped', label: '跳过' },
  { key: 'suppressed', label: '已排除' },
]

const totalsCards = computed(() => {
  const totals = report.value?.totals ?? {}
  return [
    { label: '总记录', value: totals.planned ?? 0 },
    { label: '已发送', value: totals.sent ?? 0 },
    { label: '失败', value: totals.failed ?? 0 },
    { label: '退信', value: totals.bounced ?? 0 },
    { label: '跳过', value: totals.skipped ?? 0 },
    { label: '已排除', value: totals.suppressed ?? 0 },
  ]
})

function groups(key: 'by_channel' | 'by_lang' | 'by_round') {
  const data = report.value?.[key] ?? {}
  return Object.entries(data).map(([groupKey, bucket]) => ({ key: groupKey, ...bucket }))
}

async function load() {
  loading.value = true
  try {
    report.value = await api.get<CampaignReportRow>(`/campaigns/${campaignId}/report`)
  } finally {
    loading.value = false
  }
}

async function exportReport() {
  exporting.value = true
  try {
    const result = await api.post<{ path: string }>(`/campaigns/${campaignId}/report/export`)
    ElMessage.success(`已导出：${result.path}`)
  } finally {
    exporting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.cards {
  margin-bottom: 12px;
}
.stat {
  text-align: center;
}
.stat .num {
  font-size: 22px;
  font-weight: 600;
}
.stat .label {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.section {
  margin-bottom: 12px;
}
</style>
