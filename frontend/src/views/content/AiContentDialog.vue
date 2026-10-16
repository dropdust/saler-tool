<template>
  <el-dialog
    v-model="visible"
    :title="`AI 内容辅助 · ${themeName}`"
    width="680px"
    @closed="reset"
  >
    <el-tabs v-model="tab">
      <el-tab-pane label="起草/润色母版" name="draft">
        <!-- 进行中视图（T241/FR-011）：命中同类活跃任务时呈现，杜绝重复提交面 -->
        <JobRunPanel v-if="draftPanelMode && draftJob" :job="draftJob" />
        <el-form v-else label-width="110px">
          <el-form-item label="业务要点">
            <el-input
              v-model="draftForm.brief"
              type="textarea"
              :rows="4"
              placeholder="例如：向肯尼亚输电线路承包商介绍电力金具，主打交期稳定与第三方检测报告"
            />
          </el-form-item>
          <el-form-item label="语气（可选）">
            <el-input v-model="draftForm.tone" placeholder="默认：专业、克制、以价值为先" maxlength="60" />
          </el-form-item>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="数据范围提示：以上业务要点与目标语言将发送至已配置的大模型服务；产出为草稿（AI 辅助），需人工审核后发布。"
          />
          <div v-if="draftProgress" class="progress">
            <el-progress :percentage="100" :indeterminate="true" :duration="2" :show-text="false" />
            <div class="hint">{{ draftProgress }}</div>
          </div>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="主题级多语言生成" name="translate">
        <JobRunPanel v-if="translatePanelMode && translateJob" :job="translateJob" />
        <el-form v-else label-width="110px">
          <el-form-item label="母版语言">
            <el-tag>{{ langLabel(masterLang) }}（{{ masterLang }}）</el-tag>
            <span class="hint" style="margin-left: 8px">
              将以该语言当前版本为源翻译；复用图谱词表术语保持译法一致。
            </span>
          </el-form-item>
          <el-form-item label="目标语言">
            <el-select v-model="translateForm.targets" multiple filterable style="width: 100%">
              <el-option
                v-for="lang in targetOptions"
                :key="lang.code"
                :value="lang.code"
                :label="`${lang.label}（${lang.code}）`"
              />
            </el-select>
          </el-form-item>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="数据范围提示：母版当前版本内容与所选语言将发送至已配置的大模型服务；生成结果进入草稿（AI 翻译），需人工审核后发布。已存在同语言版本时将被覆盖为新版本。"
          />
          <div v-if="translateProgress" class="progress">
            <el-progress :percentage="100" :indeterminate="true" :duration="2" :show-text="false" />
            <div class="hint">{{ translateProgress }}</div>
          </div>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <el-alert
      v-if="summary"
      type="success"
      :closable="false"
      show-icon
      class="summary"
      :title="summary"
    />

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button v-if="summary" type="success" plain @click="goTheme">去查看</el-button>
      <el-button
        v-if="tab === 'draft' && !draftPanelMode"
        type="primary"
        :loading="running"
        @click="submitDraft"
      >
        开始起草
      </el-button>
      <el-button
        v-if="tab === 'translate' && !translatePanelMode"
        type="primary"
        :loading="running"
        @click="submitTranslate"
      >
        开始生成
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import { TERMINAL_STATUSES } from '../../api/jobs'
import type { JobPayload } from '../../api/types'
import JobRunPanel from '../../components/common/JobRunPanel.vue'
import { LANGS, langLabel } from '../../constants'
import { useJobCenterStore } from '../../stores/jobCenter'

const visible = ref(false)
const emit = defineEmits<{ done: [] }>()
const router = useRouter()

const tab = ref<'draft' | 'translate'>('draft')
const running = ref(false)
const summary = ref('')
const draftProgress = ref('')
const translateProgress = ref('')

const themeId = ref(0)
const themeName = ref('')
const masterLang = ref('zh')

const draftForm = ref({ brief: '', tone: '' })
const translateForm = ref({ targets: [] as string[] })

const jobCenter = useJobCenterStore()
/** 重开命中的进行中任务（T241）：对应页签以面板呈现，不再出现表单与提交面 */
const draftPanelMode = ref(false)
const translatePanelMode = ref(false)
const draftJobId = ref<number | null>(null)
const translateJobId = ref<number | null>(null)
/** 已收尾任务 id（去重：提交等待与重开面板两条路径不重复提示） */
const handledJobs = new Set<number>()

function lookupJob(id: number | null): JobPayload | null {
  if (id == null) return null
  return jobCenter.activeJobs[id] ?? jobCenter.recentJobs.find((row) => row.id === id) ?? null
}
const draftJob = computed(() => lookupJob(draftJobId.value))
const translateJob = computed(() => lookupJob(translateJobId.value))

const targetOptions = computed(() => LANGS.filter((lang) => lang.code !== masterLang.value))

function open(theme: { id: number; name: string; master_lang: string }) {
  themeId.value = theme.id
  themeName.value = theme.name
  masterLang.value = theme.master_lang
  const draftActive = jobCenter.activeJobOfType('ai_content_draft')
  const translateActive = jobCenter.activeJobOfType('ai_content_translate')
  draftPanelMode.value = draftActive !== null
  translatePanelMode.value = translateActive !== null
  draftJobId.value = draftActive?.id ?? null
  translateJobId.value = translateActive?.id ?? null
  handledJobs.clear()
  summary.value = ''
  draftProgress.value = ''
  translateProgress.value = ''
  tab.value = draftActive ? 'draft' : translateActive ? 'translate' : 'draft'
  visible.value = true
}

function reset() {
  running.value = false
  summary.value = ''
  draftProgress.value = ''
  translateProgress.value = ''
  draftForm.value = { brief: '', tone: '' }
  translateForm.value = { targets: [] }
}

/** 终态收尾（提交等待与重开面板两条路径共用；按任务去重） */
function handleDraftTerminal(job: JobPayload) {
  if (handledJobs.has(job.id)) return
  handledJobs.add(job.id)
  if (job.status === 'completed') {
    draftProgress.value = '已完成'
    summary.value = '母版已生成为新草稿版本（AI 辅助），请人工审核后发布。'
    ElMessage.success('母版草稿已生成')
    emit('done')
  } else if (job.status === 'cancelled') {
    ElMessage.warning('任务已取消')
  } else {
    ElMessage.error(job.error ?? '任务失败')
  }
}

function handleTranslateTerminal(job: JobPayload) {
  if (handledJobs.has(job.id)) return
  handledJobs.add(job.id)
  if (job.status === 'completed') {
    translateProgress.value = '已完成'
    const result = (job.result ?? {}) as { created?: string[]; updated?: string[] }
    const created = (result.created ?? []).map((code) => langLabel(code)).join('、')
    const updated = (result.updated ?? []).map((code) => langLabel(code)).join('、')
    summary.value =
      [created ? `新增：${created}` : '', updated ? `覆盖更新：${updated}` : '']
        .filter(Boolean)
        .join('；') + '（均为草稿，待审核后发布）'
    ElMessage.success('多语言版本已生成')
    emit('done')
  } else if (job.status === 'cancelled') {
    ElMessage.warning('任务已取消')
  } else {
    ElMessage.error(job.error ?? '任务失败')
  }
}

// 阶段文案与终态一律读 store 订阅态（替代轮询）；重开面板路径同由终态收尾
watch(draftJob, (job) => {
  if (!job) return
  if (TERMINAL_STATUSES.includes(job.status)) {
    handleDraftTerminal(job)
    return
  }
  const phase = (job.progress?.phase as string) ?? ''
  draftProgress.value =
    phase === 'calling_llm' ? '大模型正在起草…' : phase === 'done' ? '已完成' : '处理中…'
})

watch(translateJob, (job) => {
  if (!job) return
  if (TERMINAL_STATUSES.includes(job.status)) {
    handleTranslateTerminal(job)
    return
  }
  const phase = (job.progress?.phase as string) ?? ''
  if (phase.startsWith('translating:')) {
    translateProgress.value = `正在生成：${langLabel(phase.split(':')[1])}`
  } else if (phase === 'done') {
    translateProgress.value = '已完成'
  } else {
    translateProgress.value = '处理中…'
  }
})

async function submitDraft() {
  if (!draftForm.value.brief.trim()) {
    ElMessage.warning('请填写业务要点')
    return
  }
  running.value = true
  summary.value = ''
  draftProgress.value = '任务已提交…'
  try {
    const { job_id } = await api.post<{ job_id: number }>('/ai/content/draft', {
      theme_id: themeId.value,
      brief: draftForm.value.brief,
      tone: draftForm.value.tone || null,
    })
    draftJobId.value = job_id
    const job = await jobCenter.waitFor(job_id)
    handleDraftTerminal(job)
  } catch {
    /* 客户端已提示 */
  } finally {
    running.value = false
  }
}

async function submitTranslate() {
  if (!translateForm.value.targets.length) {
    ElMessage.warning('请选择至少一个目标语言')
    return
  }
  running.value = true
  summary.value = ''
  translateProgress.value = '任务已提交…'
  try {
    const { job_id } = await api.post<{ job_id: number }>('/ai/content/translate', {
      theme_id: themeId.value,
      targets: translateForm.value.targets,
    })
    translateJobId.value = job_id
    const job = await jobCenter.waitFor(job_id)
    handleTranslateTerminal(job)
  } catch {
    /* 客户端已提示 */
  } finally {
    running.value = false
  }
}

function goTheme() {
  visible.value = false
  router.push('/content')
}

defineExpose({ open })
</script>

<style scoped>
.progress {
  margin-top: 12px;
}
.hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.summary {
  margin-top: 12px;
}
</style>
