<template>
  <el-dialog
    v-model="visible"
    title="AI 知识图谱扩充（结果进入待审核）"
    width="660px"
    @closed="reset"
  >
    <el-form label-width="110px">
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
      <el-form-item v-if="summary">
        <el-alert
          type="success"
          :closable="false"
          :title="`新增：节点 ${summary.nodes_created ?? 0}、关系 ${summary.edges_created ?? 0}、中文母版种子 ${summary.seeds_created ?? 0}（均待审核）`"
        />
      </el-form-item>
    </el-form>
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
      <el-button type="primary" :loading="running" @click="submit">开始扩充</el-button>
    </template>
  </el-dialog>

  <!-- 本次任务的模型调用入参/出参（T267 抽屉；append-to-body 叠在对话框上） -->
  <LlmCallsDrawer ref="callsDrawer" />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import { watchJob } from '../../api/jobs'
import LlmCallsDrawer from '../../components/common/LlmCallsDrawer.vue'
import type { GraphNode, Paginated } from '../../api/types'
import { NODE_TYPE_LABELS } from '../../constants'

const visible = ref(false)
const emit = defineEmits<{ done: [] }>()
const running = ref(false)
const progressText = ref('')
const summary = ref<Record<string, number> | null>(null)
const nodes = ref<GraphNode[]>([])
/** 本次提交产生的任务（成功/失败都保留）——明细入口按它过滤 */
const finishedJobId = ref<number | null>(null)
const callsDrawer = ref<InstanceType<typeof LlmCallsDrawer> | null>(null)
const router = useRouter()
const form = ref({
  description: '',
  from_node_ids: [] as number[],
  count: 20,
})

async function open() {
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
}

/** 查看本次任务发给模型的入参与原始出参（失败时尤其有用） */
function openCalls() {
  if (finishedJobId.value == null) return
  callsDrawer.value?.open({ jobId: finishedJobId.value, title: 'AI 调用明细 · 种子扩充' })
}

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
    const job = await watchJob(job_id, (tick) => {
      const phase = (tick.progress?.phase as string) ?? ''
      if (phase === 'calling_llm') progressText.value = '大模型正在生成候选…'
      else if (phase) progressText.value = `处理中：${phase}`
      else progressText.value = '处理中…'
    })
    finishedJobId.value = job_id // 终态后亮出「查看调用明细」（成功/失败都可以看）
    if (job.status === 'completed') {
      summary.value = (job.result ?? {}) as Record<string, number>
      ElMessage.success('扩充完成：结果已进入待审核')
      emit('done')
    } else {
      ElMessage.error(job.error ?? '任务失败')
    }
  } catch {
    /* 客户端已提示错误 */
  } finally {
    running.value = false
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
</style>
