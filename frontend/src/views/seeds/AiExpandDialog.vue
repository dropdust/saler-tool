<template>
  <el-dialog
    v-model="visible"
    title="AI 知识图谱扩充（结果进入待审核）"
    width="660px"
    @closed="reset"
  >
    <!-- 进行中视图（T239/FR-011）：重开命中同类活跃任务时呈现，杜绝重复提交面 -->
    <template v-if="panelMode && currentJob">
      <JobRunPanel :job="currentJob" />
    </template>
    <el-form v-else label-width="110px">
      <el-form-item label="行业/业务描述">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          placeholder="例如：面向电力金具（输电线路金具/紧固件）出口，目标市场为东非与中东"
        />
      </el-form-item>
      <el-form-item label="参考节点（可选）">
        <el-select
          v-model="form.from_node_ids"
          multiple
          filterable
          style="width: 100%"
          placeholder="从已有图谱节点出发扩充"
        >
          <el-option
            v-for="node in nodes"
            :key="node.id"
            :value="node.id"
            :label="`${NODE_TYPE_LABELS[node.node_type] ?? node.node_type} · ${node.name}`"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="候选数量">
        <el-input-number v-model="form.count" :min="5" :max="200" :step="5" />
      </el-form-item>
      <el-form-item>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="调用前提示：以上描述与所选节点名称将发送至已配置的大模型服务；产出为中文母版候选，全部进入「待审核」；采纳后在种子列表勾选中文种子，用「AI 翻译」生成各目标语言版本。"
        />
      </el-form-item>
      <el-form-item v-if="progressText" label="进度">
        <div style="width: 100%">
          <el-progress :percentage="100" :indeterminate="true" :duration="2" :show-text="false" />
          <div class="hint">{{ progressText }}</div>
        </div>
      </el-form-item>
    </el-form>
    <el-alert
      v-if="summary"
      class="summary"
      type="success"
      :closable="false"
      :title="`新增：节点 ${summary.nodes_created ?? 0}、关系 ${summary.edges_created ?? 0}、中文母版种子 ${summary.seeds_created ?? 0}（均待审核）`"
    />
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button
        v-if="finishedJobId"
        data-test="expand-view-calls"
        @click="openCalls"
      >
        查看调用明细
      </el-button>
      <el-button v-if="summary" type="success" plain @click="goReview">去审核</el-button>
      <el-button v-if="!panelMode" type="primary" :loading="running" @click="submit">开始扩充</el-button>
    </template>
  </el-dialog>

  <!-- 本次任务的模型调用入参/出参（T267 抽屉；append-to-body 叠在对话框上） -->
  <LlmCallsDrawer ref="callsDrawer" />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import JobRunPanel from '../../components/common/JobRunPanel.vue'
import LlmCallsDrawer from '../../components/common/LlmCallsDrawer.vue'
import type { GraphNode, JobPayload, Paginated } from '../../api/types'
import { NODE_TYPE_LABELS } from '../../constants'
import { TERMINAL_STATUSES } from '../../api/jobs'
import { parseServerTime, useJobCenterStore } from '../../stores/jobCenter'

const visible = ref(false)
const emit = defineEmits<{ done: [] }>()
const jobCenter = useJobCenterStore()
const running = ref(false)
const progressText = ref('')
const summary = ref<Record<string, number> | null>(null)
const nodes = ref<GraphNode[]>([])
/** 本次提交产生的任务（成功/失败都保留）——明细入口按它过滤 */
const finishedJobId = ref<number | null>(null)
/** 重开命中的进行中任务（T239）：以面板呈现，不再出现表单与「开始扩充」 */
const panelMode = ref(false)
const currentJobId = ref<number | null>(null)
const doneHandled = ref(false)
const callsDrawer = ref<InstanceType<typeof LlmCallsDrawer> | null>(null)
const router = useRouter()
const form = ref({
  description: '',
  from_node_ids: [] as number[],
  count: 20,
})

/** 当前任务（store 同源）：活跃期读订阅态，终态迁移后落到 recent 仍可查 */
const currentJob = computed<JobPayload | null>(() => {
  const id = currentJobId.value
  if (id == null) return null
  return jobCenter.activeJobs[id] ?? jobCenter.recentJobs.find((row) => row.id === id) ?? null
})

async function open() {
  const active = jobCenter.activeJobOfType('ai_seed_expand')
  panelMode.value = active !== null
  currentJobId.value = active?.id ?? null
  doneHandled.value = false
  visible.value = true
  if (!nodes.value.length) {
    const page = await api.get<Paginated<GraphNode>>('/graph/nodes', { page_size: 500 })
    nodes.value = page.items.filter((node) => node.status === 'active')
  }
}

function reset() {
  progressText.value = ''
  summary.value = null
  running.value = false
  finishedJobId.value = null
  stopTick()
}

/**
 * 已等待秒数（自任务开始）：随 1s tick 刷新——前台卡住时也能看出等了多久，
 * 配合「调用明细」判断是阻塞在单次请求还是多次重试。
 */
function waitedSeconds(startedAt: string | null): number {
  const started = parseServerTime(startedAt)
  if (started == null) return 0
  return Math.max(0, Math.floor((Date.now() - started) / 1000))
}

let tickTimer: ReturnType<typeof setInterval> | null = null

function stopTick() {
  if (tickTimer !== null) {
    clearInterval(tickTimer)
    tickTimer = null
  }
}

/** 留框等待的进度文案（FR-013）：阶段与已等待一律读 store 订阅态 */
function refreshProgressText() {
  const id = currentJobId.value
  const job = id == null ? null : jobCenter.activeJobs[id]
  if (!job) return
  const phase = (job.progress?.phase as string) ?? ''
  const waited = `（已等待 ${waitedSeconds(job.started_at)} 秒）`
  if (phase === 'calling_llm') progressText.value = `大模型正在生成候选…${waited}`
  else if (phase) progressText.value = `处理中：${phase}${waited}`
  else progressText.value = `处理中…${waited}`
}

/** 查看本次任务发给模型的入参与原始出参（失败时尤其有用） */
function openCalls() {
  if (finishedJobId.value == null) return
  callsDrawer.value?.open({ jobId: finishedJobId.value, title: 'AI 调用明细 · 种子扩充' })
}

/** 终态收尾（提交等待与重开面板两条路径共用；按任务去重，不重复提示） */
function handleTerminal(job: JobPayload) {
  finishedJobId.value = job.id
  if (doneHandled.value) return
  doneHandled.value = true
  stopTick()
  if (job.status === 'completed') {
    summary.value = (job.result ?? {}) as Record<string, number>
    ElMessage.success('扩充完成：结果已进入待审核')
    emit('done')
  } else if (job.status === 'cancelled') {
    ElMessage.warning('任务已取消')
  } else {
    ElMessage.error(job.error ?? '任务失败')
  }
}

// 重开面板路径：对话框开着看任务跑到终态（提交路径由 waitFor 收尾，经 doneHandled 去重）
watch(currentJob, (job) => {
  if (job && TERMINAL_STATUSES.includes(job.status)) handleTerminal(job)
})

async function submit() {
  if (!form.value.description.trim() && !form.value.from_node_ids.length) {
    ElMessage.warning('请填写业务描述或选择参考节点')
    return
  }
  running.value = true
  summary.value = null
  progressText.value = '任务已提交…'
  try {
    const { job_id } = await api.post<{ job_id: number }>('/ai/seeds/expand', form.value)
    currentJobId.value = job_id
    doneHandled.value = false
    tickTimer = setInterval(refreshProgressText, 1000)
    const job = await jobCenter.waitFor(job_id)
    handleTerminal(job)
  } catch {
    /* 客户端已提示错误 */
  } finally {
    running.value = false
    stopTick()
    progressText.value = summary.value ? '已完成' : progressText.value
  }
}

function goReview() {
  visible.value = false
  router.push('/seeds/review')
}

defineExpose({ open })
</script>

<style scoped>
.hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.summary {
  margin-top: 12px;
}
</style>
