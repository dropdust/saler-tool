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

    <!-- 监控卡片：状态与进度一律读全局任务中心 store（同源一致 FR-008；进入页面自动选中活跃任务） -->
    <el-card v-if="selectedJob" class="monitor" shadow="never" data-test="monitor-card">
      <template #header>
        <b>任务 #{{ selectedJob.id }}</b>
        <StatusTag :status="selectedJob.status" class="tag" />
        <span class="spacer" />
        <el-button
          v-if="selectedJob.can_pause && selectedJob.status === 'running'"
          size="small"
          @click="control('pause')"
        >
          暂停
        </el-button>
        <el-button
          v-if="selectedJob.can_pause && selectedJob.status === 'paused'"
          size="small"
          type="success"
          @click="control('resume')"
        >
          恢复
        </el-button>
        <el-button
          v-if="['running', 'paused', 'queued'].includes(selectedJob.status)"
          size="small"
          type="danger"
          @click="control('cancel')"
        >
          取消
        </el-button>
      </template>
      <el-progress
        :percentage="view?.percent ?? 0"
        :indeterminate="view?.indeterminate ?? true"
        :stroke-width="14"
        :format="() => view?.text ?? ''"
      />
      <div v-if="logLines.length" class="logs">
        <div v-for="(line, index) in logLines" :key="index" class="log-line">{{ line.message }}</div>
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
            <el-button size="small" text type="primary" @click="monitor(row.id)">监控</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="createVisible" title="启动挖掘任务" width="660px">
      <el-form label-width="120px">
        <el-form-item v-if="sameTypeActive" label="进行中">
          <el-alert
            type="warning"
            :closable="false"
            show-icon
            :title="`已有进行中的挖掘任务（#${sameTypeActive.id}）——任务中心可见进度；同时运行可能重复抓取同一批域名`"
          />
        </el-form-item>
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
        <!-- 数值参数：三列并排时列内放不下「左 label + 150px 控件」，label 置顶并让控件撑满列宽，
             否则 el-input-number 被 flex 压缩后内部输入区塌缩为 0，数值无法查看与键入 -->
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="并发" label-position="top">
              <el-input-number v-model="config.concurrency" :min="1" :max="10" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="单站间隔（秒）" label-position="top">
              <el-input-number
                v-model="config.per_host_delay_s"
                :min="0.2"
                :max="10"
                :step="0.2"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="单站页数" label-position="top">
              <el-input-number
                v-model="config.max_pages_per_site"
                :min="1"
                :max="20"
                style="width: 100%"
              />
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
import { computed, onMounted, ref, watch as watchRef } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import { useJobCenterStore } from '../../stores/jobCenter'
import type { CrawlJobRow, JobPayload, Paginated, Seed } from '../../api/types'
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

const store = useJobCenterStore()
// 选中的挖掘明细（crawl_job id）；对应的通用任务从 store 反查（活跃优先 → 最近终态）
const selectedCrawlJobId = ref<number | null>(null)

function matchCrawl(job: JobPayload, crawlJobId: number): boolean {
  return job.ref_type === 'crawl_job' && job.ref_id === crawlJobId
}

const selectedJob = computed<JobPayload | null>(() => {
  const id = selectedCrawlJobId.value
  if (id === null) return null
  return (
    store.activeList.find((job) => matchCrawl(job, id)) ??
    store.recentJobs.find((job) => matchCrawl(job, id)) ??
    null
  )
})
const view = computed(() => (selectedJob.value ? store.progressView(selectedJob.value) : null))
const logLines = computed(() => {
  const id = selectedJob.value?.id
  if (id === undefined) return []
  return [...(store.logs[id] ?? [])].reverse()
})
const sameTypeActive = computed(() => store.activeJobOfType('crawl'))

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

function autoSelect() {
  if (selectedCrawlJobId.value !== null) return
  const job = sameTypeActive.value
  if (job && job.ref_type === 'crawl_job' && job.ref_id != null) {
    selectedCrawlJobId.value = job.ref_id
  }
}

// store.init 在 MainLayout（父层）挂载完成后才填充——watch 覆盖两种到达顺序（FR-006 自动恢复展示）
watchRef(() => store.activeList, autoSelect, { immediate: true })

function monitor(crawlJobId: number) {
  const id = crawlJobId
  const job =
    store.activeList.find((row) => matchCrawl(row, id)) ??
    store.recentJobs.find((row) => matchCrawl(row, id))
  if (!job) {
    ElMessage.info('该任务不在实时保留窗口内（任务中心仅保留最近 24 小时）；统计见下方列表')
    return
  }
  selectedCrawlJobId.value = id
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
    const { job_id, crawl_job_id } = await api.post<{ job_id: number; crawl_job_id: number }>(
      '/crawl/jobs',
      {
        seed_ids: scopeMode.value === 'select' ? seedIds.value : null,
        config: config.value,
      },
    )
    createVisible.value = false
    selectedCrawlJobId.value = crawl_job_id
    // 登记进任务中心（立即订阅，不等下一次列表刷新）
    await store.register(job_id)
    ElMessage.success('挖掘任务已启动（进度可在任务中心随时查看）')
    loadJobs()
  } finally {
    starting.value = false
  }
}

async function control(action: 'pause' | 'resume' | 'cancel') {
  const job = selectedJob.value
  if (!job) return
  await store.control(job.id, action)
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
