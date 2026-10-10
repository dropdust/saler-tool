<template>
  <div>
    <PageHeader
      title="挖掘任务"
      description="种子 → 检索 → 抓取 → 联系方式抽取；支持暂停/恢复，断点续跑（状态在数据库）。"
    >
      <template #actions>
        <el-button type="primary" @click="openCreate">启动挖掘</el-button>
        <el-button @click="loadJobs">刷新</el-button>
      </template>
    </PageHeader>

    <el-card v-if="activeJobId" class="monitor" shadow="never">
      <template #header>
        <b>任务 #{{ activeJobId }}</b>
        <StatusTag :status="activeStatus" class="tag" />
        <span class="spacer" />
        <el-button v-if="activeStatus === 'running'" size="small" @click="control('pause')">暂停</el-button>
        <el-button v-if="activeStatus === 'paused'" size="small" type="success" @click="control('resume')">恢复</el-button>
        <el-button
          v-if="['running', 'paused', 'queued'].includes(activeStatus)"
          size="small"
          type="danger"
          @click="control('cancel')"
        >取消</el-button>
      </template>
      <el-progress :percentage="progressPercent" :stroke-width="14" :format="() => progressText" />
      <div class="logs">
        <div v-for="(line, index) in recentLines" :key="index" class="log-line">{{ line }}</div>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="jobs">
        <el-table-column prop="id" label="#" width="70" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="范围" min-width="180">
          <template #default="{ row }">
            {{ row.scope?.seed_ids?.length ? `指定种子 ${row.scope.seed_ids.length} 条` : '全部待执行种子' }}
          </template>
        </el-table-column>
        <el-table-column label="统计" min-width="280">
          <template #default="{ row }">{{ statsText(row as CrawlJobRow) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ (row.created_at || '').slice(0, 19).replace('T', ' ') }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="watch(row.id)">监控</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="createVisible" title="启动挖掘任务" width="660px">
      <el-form label-width="120px">
        <el-form-item label="种子范围">
          <el-radio-group v-model="scopeMode">
            <el-radio value="pending">全部待执行（已采纳）</el-radio>
            <el-radio value="select">指定种子</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="scopeMode === 'select'" label="选择种子">
          <el-select v-model="seedIds" multiple filterable style="width: 100%" placeholder="仅列出已采纳、待执行的种子">
            <el-option v-for="seed in candidateSeeds" :key="seed.id" :value="seed.id" :label="seed.query" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="并发">
              <el-input-number v-model="config.concurrency" :min="1" :max="10" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="单站间隔（秒）">
              <el-input-number v-model="config.per_host_delay_s" :min="0.2" :max="10" :step="0.2" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="单站页数">
              <el-input-number v-model="config.max_pages_per_site" :min="1" :max="20" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="遵循 robots.txt"><el-switch v-model="config.respect_robots" /></el-form-item>
        <el-form-item label="网络代理">
          <el-input v-model="config.proxy" placeholder="留空沿用全局设置" />
        </el-form-item>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="抓取遵循礼貌策略（限速/重试/断点续跑）；任务可随时暂停或取消。"
        />
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="starting" @click="startCrawl">启动</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import { useJobEvents } from '../../composables/useJobEvents'
import type { CrawlJobRow, Paginated, Seed } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import StatusTag from '../../components/common/StatusTag.vue'

const jobs = ref<CrawlJobRow[]>([])
const loading = ref(false)
const createVisible = ref(false)
const starting = ref(false)
const scopeMode = ref<'pending' | 'select'>('pending')
const seedIds = ref<number[]>([])
const candidateSeeds = ref<Seed[]>([])
const config = ref({
  concurrency: 5,
  per_host_delay_s: 1,
  max_pages_per_site: 6,
  respect_robots: true,
  proxy: '',
})

const activeJobId = ref<number | null>(null)
const activeStatus = ref('queued')
const activeProgress = ref<Record<string, number>>({})
const recentLines = ref<string[]>([])
const { subscribe } = useJobEvents()

const progressPercent = computed(() => {
  if (activeStatus.value === 'completed') return 100
  const p = activeProgress.value
  if (p.total_seeds) return Math.min(99, Math.round(((p.seeds_processed ?? 0) / p.total_seeds) * 50))
  if (p.total_domains) return Math.min(99, 50 + Math.round(((p.fetched_domains ?? 0) / p.total_domains) * 50))
  return activeStatus.value === 'running' ? 5 : 0
})
const progressText = computed(() => {
  if (activeStatus.value === 'completed') return '已完成'
  if (activeStatus.value === 'failed') return '失败'
  const p = activeProgress.value
  if (p.total_seeds) return `检索：${p.seeds_processed ?? 0}/${p.total_seeds} 条种子`
  if (p.total_domains) return `抓取：${p.fetched_domains ?? 0}/${p.total_domains} 个域名`
  return '准备中…'
})

async function loadJobs() {
  loading.value = true
  try {
    const page = await api.get<Paginated<CrawlJobRow>>('/crawl/jobs', { page_size: 50 })
    jobs.value = page.items
  } finally {
    loading.value = false
  }
}

function statsText(row: CrawlJobRow): string {
  const s = row.stats || {}
  if (!s || !Object.keys(s).length) return '—'
  return `种子 ${s.seeds_processed ?? 0} · 域名 ${s.domains_found ?? 0} · 完成 ${s.domains_done ?? 0} · 联系方式 ${s.contacts_created ?? 0}`
}

function pushLine(text: string) {
  recentLines.value.unshift(text)
  if (recentLines.value.length > 60) recentLines.value.pop()
}

function watch(jobId: number) {
  activeJobId.value = jobId
  activeStatus.value = 'queued'
  activeProgress.value = {}
  recentLines.value = []
  subscribe(jobId, {
    onProgress: (data) => {
      const snapshot = (data as { snapshot?: { status?: string } }).snapshot
      if (snapshot?.status) activeStatus.value = snapshot.status
      const numeric = Object.fromEntries(
        Object.entries(data).filter(([, value]) => typeof value === 'number'),
      ) as Record<string, number>
      activeProgress.value = { ...activeProgress.value, ...numeric }
    },
    onLog: (data) => pushLine(data.message),
    onDone: (data) => {
      activeStatus.value = 'completed'
      const result = (data as { result?: Record<string, number> }).result
      pushLine(`完成：新增联系方式 ${result?.contacts_created ?? 0}，域名 ${result?.domains_done ?? 0}`)
      ElMessage.success('挖掘任务完成')
      loadJobs()
    },
    onError: (data) => {
      activeStatus.value = 'failed'
      pushLine(`错误：${(data as { message?: string }).message ?? '任务失败'}`)
    },
  })
}

async function openCreate() {
  createVisible.value = true
  const page = await api.get<Paginated<Seed>>('/seeds', {
    review_status: 'approved',
    status: 'pending',
    page_size: 200,
    sort: 'priority',
  })
  candidateSeeds.value = page.items
}

async function startCrawl() {
  starting.value = true
  try {
    const { job_id } = await api.post<{ job_id: number }>('/crawl/jobs', {
      seed_ids: scopeMode.value === 'select' ? seedIds.value : null,
      config: config.value,
    })
    createVisible.value = false
    watch(job_id)
    ElMessage.success('挖掘任务已启动')
    loadJobs()
  } finally {
    starting.value = false
  }
}

async function control(action: 'pause' | 'resume' | 'cancel') {
  if (!activeJobId.value) return
  await api.post(`/jobs/${activeJobId.value}/${action}`)
  activeStatus.value = action === 'pause' ? 'paused' : action === 'resume' ? 'running' : 'cancelled'
}

onMounted(loadJobs)
</script>

<style scoped>
.monitor {
  margin-bottom: 12px;
}
.tag {
  margin-left: 8px;
}
.spacer {
  flex: 1;
  display: inline-block;
  width: 40%;
}
.logs {
  margin-top: 10px;
  max-height: 180px;
  overflow-y: auto;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  padding: 8px 10px;
  font-family: monospace;
  font-size: 12px;
}
.log-line {
  line-height: 1.7;
  color: var(--el-text-color-regular);
}
</style>
