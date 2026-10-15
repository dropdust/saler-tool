<template>
  <el-drawer
    v-model="visible"
    append-to-body
    direction="rtl"
    size="62%"
    :title="title"
    class="llm-calls-drawer"
  >
    <div v-loading="loading" class="llm-calls-body">
      <el-alert
        v-if="loadError"
        type="error"
        :closable="false"
        title="调用明细加载失败（可重试；若任务刚创建，模型可能还在生成）"
        data-test="llm-load-error"
      >
        <el-button size="small" data-test="llm-retry" @click="load({ resetExpanded: true })">重试</el-button>
      </el-alert>

      <EmptyState v-else-if="!groups.length" :description="emptyText" />

      <div v-for="group in groups" :key="group.key" class="call-card" data-test="llm-call">
        <button
          type="button"
          class="call-head"
          :aria-expanded="expanded.has(group.key)"
          data-test="llm-call-head"
          @click="toggle(group.key)"
        >
          <span class="seq">№{{ group.callIndex }}</span>
          <span>{{ operationLabel(group.operation) }}</span>
          <span v-if="phaseText(group.phase)">{{ phaseText(group.phase) }}</span>
          <span class="muted">{{ group.provider }}/{{ group.model }}</span>
          <span class="muted" data-test="llm-group-timing">
            尝试 {{ group.attempts.length }} 次 · {{ groupTiming(group, now) }}
          </span>
          <span class="muted">{{ formatTs(group.ts) }}</span>
          <span v-if="jobId == null" class="muted">任务 #{{ group.jobId }}</span>
          <el-tag v-if="group.ok === null" type="warning" size="small" data-test="llm-running-tag">
            进行中
          </el-tag>
          <el-tag v-else :type="group.ok ? 'success' : 'danger'" size="small">
            {{ group.ok ? '成功' : '失败' }}
          </el-tag>
        </button>

        <div v-if="expanded.has(group.key)" class="call-body">
          <section
            v-for="attempt in group.attempts"
            :key="attempt.id"
            class="attempt"
            data-test="llm-attempt"
          >
            <div class="attempt-head">
              <b>第 {{ attempt.attempt }} 次尝试</b>
              <el-tag v-if="attempt.ok === null" type="warning" size="small">进行中</el-tag>
              <el-tag v-else :type="attempt.ok ? 'success' : 'danger'" size="small">
                {{ attempt.ok ? '成功' : '失败' }}
              </el-tag>
              <span class="muted" data-test="llm-attempt-timing">{{ attemptTiming(attempt, now) }}</span>
              <span class="muted">{{ usageText(attempt.usage) }}</span>
              <span class="muted">{{ formatTs(attempt.ts) }}</span>
            </div>

            <div class="block-head">
              <span class="block-title">入参（发送给模型）</span>
              <el-button size="small" text type="primary" data-test="copy-input" @click="copy(inputText(attempt))">
                复制
              </el-button>
            </div>
            <div v-for="(message, index) in attempt.request_messages" :key="index" class="message">
              <span class="role">{{ roleLabel(message.role) }}</span>
              <pre class="pre">{{ messageText(message.content) }}</pre>
            </div>

            <div class="block-head">
              <span class="block-title">出参（模型原始输出）</span>
              <el-button
                size="small"
                text
                type="primary"
                data-test="copy-output"
                @click="copy(attempt.response_text ?? '')"
              >
                复制
              </el-button>
            </div>
            <pre class="pre" data-test="llm-output">{{
              attempt.ok === null ? '（模型尚未返回）' : attempt.response_text || '（无输出）'
            }}</pre>

            <template v-if="attempt.ok === false">
              <div class="block-head">
                <span class="block-title">错误</span>
              </div>
              <pre class="pre" data-test="llm-error">{{ errorText(attempt) }}</pre>
            </template>
          </section>
        </div>
      </div>

      <el-pagination
        v-if="total > LIMIT"
        class="pager"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="LIMIT"
        :current-page="page"
        @current-change="onPageChange"
      />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
/**
 * LLM 调用明细抽屉（T267）：按任务/操作查看每次调用的入参（完整 messages）、
 * 出参（模型原始输出）、逐次尝试的耗时与用量、失败原因；修复重试合为一张卡。
 * 数据源 GET /ai/calls（local-api.md）。折叠卡不渲染正文——避免大 prompt/大输出卡顿。
 *
 * T271：进行中的尝试（ok=null，请求已发出、尚未返回）显示「进行中 + 已等待」并自动轮询
 * （请求发出前即可见入参——卡住时据此判断阻塞在第一次请求还是多次重试），收口即停。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { api } from '../../api/client'
import type { LlmCallPage, LlmCallRow } from '../../api/types'
import EmptyState from './EmptyState.vue'
import {
  attemptTiming,
  formatTs,
  groupAttempts,
  groupTiming,
  messageText,
  operationLabel,
  phaseText,
  roleLabel,
  usageText,
} from './llmCalls'

/** 每页行数（行 = 一次尝试）；修复链跨页断卡为已知限制 */
const LIMIT = 20
/** 进行中自动刷新间隔（静默刷新，不遮罩） */
const REFRESH_MS = 2000

const visible = ref(false)
const loading = ref(false)
const loadError = ref(false)
const items = ref<LlmCallRow[]>([])
const total = ref(0)
const page = ref(1)
const jobId = ref<number | null>(null)
const operation = ref<string | null>(null)
const titleOverride = ref<string | null>(null)
const expanded = ref<Set<string>>(new Set())
/** 渲染「已等待」的时间基准：每次加载刷新（进行中每 2s 一次） */
const now = ref(Date.now())
let refreshTimer: ReturnType<typeof setTimeout> | null = null

const groups = computed(() => groupAttempts(items.value))
const hasRunning = computed(() => items.value.some((item) => item.ok === null))

function clearRefresh() {
  if (refreshTimer !== null) {
    clearTimeout(refreshTimer)
    refreshTimer = null
  }
}

/** 仅当抽屉开着且仍有进行中的尝试时才续约轮询 */
function scheduleRefresh() {
  clearRefresh()
  if (!visible.value || !hasRunning.value) return
  refreshTimer = setTimeout(() => void load({ silent: true }), REFRESH_MS)
}

watch(visible, (open) => {
  if (!open) clearRefresh()
})
onBeforeUnmount(clearRefresh)
const title = computed(
  () =>
    titleOverride.value ??
    (jobId.value != null ? `AI 调用明细 · 任务 #${jobId.value}` : 'AI 调用明细'),
)
const emptyText = computed(() => (jobId.value != null ? '该任务暂无调用记录' : '暂无调用记录'))

function open(options: { jobId?: number; operation?: string; title?: string } = {}) {
  jobId.value = options.jobId ?? null
  operation.value = options.operation ?? null
  titleOverride.value = options.title ?? null
  page.value = 1
  items.value = []
  total.value = 0
  loadError.value = false
  expanded.value = new Set()
  visible.value = true
  void load({ resetExpanded: true })
}

async function load(options: { resetExpanded?: boolean; silent?: boolean } = {}) {
  if (!options.silent) loading.value = true
  loadError.value = false
  now.value = Date.now()
  let refreshFailed = false
  try {
    const params: Record<string, string | number> = { limit: LIMIT, offset: (page.value - 1) * LIMIT }
    if (jobId.value != null) params.job_id = jobId.value
    if (operation.value) params.operation = operation.value
    const payload = await api.get<LlmCallPage>('/ai/calls', params)
    items.value = payload?.items ?? []
    total.value = payload?.total ?? 0
    if (options.resetExpanded) {
      const [first] = groupAttempts(items.value)
      // 默认展开最新一次调用；大文本只渲染这一张卡（自动刷新不复位，避免打断阅读）
      expanded.value = new Set(first ? [first.key] : [])
    }
  } catch {
    loadError.value = true
    refreshFailed = options.silent === true
    if (!refreshFailed) {
      items.value = []
      total.value = 0
    }
  } finally {
    if (!options.silent) loading.value = false
    // 静默刷新失败：保留既有明细、停止轮询（用户可「重试」），避免每 2s 反复报错
    if (!refreshFailed) scheduleRefresh()
  }
}

function onPageChange(next: number) {
  page.value = next
  void load({ resetExpanded: true })
}

function toggle(key: string) {
  const next = new Set(expanded.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expanded.value = next
}

function inputText(attempt: LlmCallRow): string {
  return attempt.request_messages
    .map((message) => `【${roleLabel(message.role)}】\n${messageText(message.content)}`)
    .join('\n\n')
}

function errorText(attempt: LlmCallRow): string {
  return [attempt.error_kind, attempt.error_detail].filter(Boolean).join('\n') || '（无详情）'
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制')
  } catch {
    // 明细文本可达数百 KB，降级不弹全文（与本仓 ImportExport 的降级口径不同）
    ElMessage.error('当前环境不支持自动复制，请手动选择文本复制')
  }
}

defineExpose({ open })
</script>

<style scoped>
.llm-calls-body {
  min-height: 120px;
}
.call-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  margin-bottom: 10px;
  overflow: hidden;
}
.call-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border: 0;
  cursor: pointer;
  text-align: left;
  font: inherit;
  font-size: 13px;
  color: inherit;
}
.seq {
  font-weight: 600;
}
.call-body {
  padding: 4px 12px 10px;
}
.attempt {
  padding-top: 8px;
}
.attempt + .attempt {
  border-top: 1px dashed var(--el-border-color-lighter);
  margin-top: 10px;
}
.attempt-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  margin-bottom: 6px;
}
.block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 8px 0 4px;
}
.block-title {
  font-size: 12.5px;
  color: var(--el-text-color-secondary);
}
.message {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.role {
  flex: none;
  min-width: 28px;
  padding-top: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.pre {
  flex: 1;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 10px;
  margin: 0 0 8px;
  font-family: inherit;
  font-size: 12.5px;
  line-height: 1.6;
  max-height: 52vh;
  overflow: auto;
}
.muted {
  color: var(--el-text-color-secondary);
}
.pager {
  margin-top: 8px;
  justify-content: flex-end;
}
</style>
