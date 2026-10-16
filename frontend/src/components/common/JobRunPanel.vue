<template>
  <div class="job-run-panel" data-test="job-run-panel">
    <div class="row header">
      <b class="job-name">{{ job.name ?? `任务 #${job.id}` }}</b>
      <StatusTag :status="job.status" />
      <span class="spacer" />
      <span class="elapsed">{{ elapsedText }}</span>
    </div>

    <template v-if="active">
      <el-progress
        :percentage="view.percent"
        :indeterminate="view.indeterminate"
        :stroke-width="10"
        :format="() => view.text"
      />
      <div class="log-title">日志</div>
      <pre class="logs" data-test="job-run-logs">{{ logText }}</pre>
      <div class="row meta">
        <el-button size="small" type="danger" data-test="job-run-cancel" @click="cancel">
          取消任务
        </el-button>
      </div>
      <el-alert
        class="hint-alert"
        type="info"
        :closable="false"
        show-icon
        data-test="job-run-hint"
        title="关闭本窗口不会中断任务，进度可在任务中心查看"
      />
    </template>

    <el-alert
      v-else-if="job.status === 'completed'"
      class="result-alert"
      type="success"
      :closable="false"
      show-icon
      :title="summary ? `已完成 · ${summary}` : '已完成'"
    />
    <el-alert
      v-else
      class="result-alert"
      type="error"
      :closable="false"
      show-icon
      :title="summary || '任务失败'"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * 对话框「进行中视图」通用件（005 T238，契约 §5「对话框转后台」行）：
 * 状态标签 + 进度/阶段文案（store.progressView）+ 日志尾（store 缓冲）+ 取消任务 +
 * 「关闭本窗口不会中断任务」常驻提示；终态分支呈现结果摘要（成功/失败/已取消/已中断）。
 * 进度与状态一律读任务中心 store——与任务中心同源（唯一订阅方，FR-008）。
 */

import { computed, onBeforeUnmount, ref } from 'vue'

import StatusTag from './StatusTag.vue'
import type { JobPayload } from '../../api/types'
import { ACTIVE_STATUSES, parseServerTime, useJobCenterStore } from '../../stores/jobCenter'

const props = defineProps<{ job: JobPayload }>()
const store = useJobCenterStore()

const active = computed(() => ACTIVE_STATUSES.includes(props.job.status))
const view = computed(() => store.progressView(props.job))
const summary = computed(() => store.resultSummary(props.job))

const LOG_TAIL = 10
const logText = computed(() => {
  const lines = store.logs[props.job.id] ?? []
  if (!lines.length) return '暂无日志'
  return lines
    .slice(-LOG_TAIL)
    .map((line) => line.message)
    .join('\n')
})

// 耗时（契约 §5）：进行中本地每秒 tick，终态取 finished_at − started_at
const now = ref(Date.now())
const timer = setInterval(() => {
  now.value = Date.now()
}, 1000)
onBeforeUnmount(() => clearInterval(timer))

function formatDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  if (hours) return `${hours} 小时 ${minutes} 分`
  if (minutes) return `${minutes} 分 ${seconds} 秒`
  return `${seconds} 秒`
}

const elapsedText = computed(() => {
  const start = parseServerTime(props.job.started_at)
  if (start === null) return ''
  const end = parseServerTime(props.job.finished_at) ?? (active.value ? now.value : start)
  return formatDuration(Math.max(0, end - start))
})

async function cancel() {
  if (!active.value) return
  try {
    await store.control(props.job.id, 'cancel')
  } catch {
    /* 客户端已提示（服务端回执） */
  }
}
</script>

<style scoped>
.job-run-panel .row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.header {
  margin-bottom: 10px;
}
.job-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.spacer {
  flex: 1;
}
.elapsed {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.log-title {
  margin: 10px 0 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.logs {
  margin: 0;
  padding: 8px 10px;
  max-height: 140px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-light);
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-all;
}
.meta {
  margin-top: 10px;
}
.hint-alert,
.result-alert {
  margin-top: 10px;
}
</style>
