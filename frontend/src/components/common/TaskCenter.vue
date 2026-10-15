<template>
  <div class="task-center">
    <el-badge :value="store.activeCount" :hidden="store.activeCount === 0" class="badge">
      <el-button size="small" text data-test="task-center-trigger" @click="drawerOpen = true">
        <el-icon :class="{ 'is-spinning': store.activeCount > 0 }"><Loading /></el-icon>
        <span>任务</span>
      </el-button>
    </el-badge>

    <el-drawer v-model="drawerOpen" title="任务中心" direction="rtl" size="440px">
      <div v-if="!store.activeList.length && !store.recentJobs.length" class="empty">暂无任务</div>

      <template v-else>
        <h4 v-if="store.activeList.length" class="group-title">
          进行中（{{ store.activeList.length }}）
        </h4>
        <el-card
          v-for="job in store.activeList"
          :key="job.id"
          shadow="never"
          class="job-card"
          data-test="active-job"
        >
          <div class="row">
            <b class="job-name">{{ job.name ?? `任务 #${job.id}` }}</b>
            <StatusTag :status="job.status" />
          </div>
          <el-progress
            :percentage="view(job).percent"
            :indeterminate="view(job).indeterminate"
            :stroke-width="10"
            :format="() => view(job).text"
          />
          <div class="row meta">
            <span class="elapsed">{{ elapsed(job) }}</span>
            <span class="spacer" />
            <el-button
              v-if="job.can_pause && job.status === 'running'"
              size="small"
              @click="control(job, 'pause')"
            >
              暂停
            </el-button>
            <el-button
              v-if="job.can_pause && job.status === 'paused'"
              size="small"
              type="success"
              @click="control(job, 'resume')"
            >
              恢复
            </el-button>
            <el-button size="small" type="danger" @click="control(job, 'cancel')">取消</el-button>
            <el-button
              v-if="isAiJobType(job.job_type)"
              size="small"
              text
              type="primary"
              data-test="job-calls"
              @click="openCalls(job)"
            >
              调用明细
            </el-button>
            <el-button size="small" text type="primary" @click="go(job)">查看</el-button>
          </div>
        </el-card>

        <h4 v-if="store.recentJobs.length" class="group-title">最近完成</h4>
        <el-card
          v-for="job in store.recentJobs"
          :key="job.id"
          shadow="never"
          class="job-card"
          data-test="recent-job"
        >
          <div class="row">
            <b class="job-name">{{ job.name ?? `任务 #${job.id}` }}</b>
            <StatusTag :status="job.status" />
          </div>
          <div class="row meta">
            <span class="summary">{{ store.resultSummary(job) }}</span>
            <span
              v-if="job.status === 'interrupted' && !job.rerunnable"
              class="muted"
              data-test="rerun-guide"
            >
              不支持重跑，请前往相关页面重新发起
            </span>
            <span class="spacer" />
            <el-button
              v-if="job.rerunnable && job.status !== 'completed'"
              size="small"
              type="warning"
              plain
              data-test="job-rerun"
              @click="rerun(job)"
            >
              重新运行
            </el-button>
            <el-button
              v-if="isAiJobType(job.job_type)"
              size="small"
              text
              type="primary"
              data-test="job-calls"
              @click="openCalls(job)"
            >
              调用明细
            </el-button>
            <el-button size="small" text type="primary" @click="go(job)">查看</el-button>
          </div>
        </el-card>
      </template>
    </el-drawer>

    <!-- AI 任务：查看逐次模型调用的入参/出参（T267 组件，append-to-body 叠在本抽屉之上） -->
    <LlmCallsDrawer ref="callsDrawer" />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'

import StatusTag from './StatusTag.vue'
import LlmCallsDrawer from './LlmCallsDrawer.vue'
import { isAiJobType, jobRoute } from '../../constants'
import type { JobPayload } from '../../api/types'
import { parseServerTime, useJobCenterStore } from '../../stores/jobCenter'

const store = useJobCenterStore()
const router = useRouter()
const drawerOpen = ref(false)
const callsDrawer = ref<InstanceType<typeof LlmCallsDrawer> | null>(null)

// 已耗时本地每秒 tick（显示用，不写回 store）
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

function elapsed(job: JobPayload): string {
  const start = parseServerTime(job.started_at)
  if (start === null) return ''
  const end = parseServerTime(job.finished_at) ?? now.value
  return formatDuration(end - start)
}

function view(job: JobPayload) {
  return store.progressView(job)
}

async function control(job: JobPayload, action: 'pause' | 'resume' | 'cancel') {
  await store.control(job.id, action)
}

/** 重新运行已失败/已取消/已中断的可重跑任务；守卫失败的文案由 api 客户端按服务端回执提示 */
async function rerun(job: JobPayload) {
  try {
    await store.rerun(job.id)
    ElMessage.success('已重新运行')
  } catch {
    /* 客户端已提示（not_rerunnable / not_terminal / already_completed） */
  }
}

function go(job: JobPayload) {
  const route = jobRoute(job.job_type)
  if (!route) return // 未映射类型：保持抽屉打开定位该任务（契约 §5 回退口径）
  drawerOpen.value = false
  void router.push(route)
}

/** 打开该任务的 LLM 调用明细（不改导航、不关任务抽屉——明细叠在其上） */
function openCalls(job: JobPayload) {
  callsDrawer.value?.open({ jobId: job.id, title: `AI 调用明细 · 任务 #${job.id}` })
}
</script>

<style scoped>
.task-center {
  display: inline-flex;
  align-items: center;
}
.badge {
  margin-right: 10px;
}
.is-spinning {
  animation: spin 1.2s linear infinite;
}
@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
.group-title {
  margin: 4px 0 10px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.job-card {
  margin-bottom: 10px;
}
.job-card :deep(.el-card__body) {
  padding: 12px;
}
.row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.muted {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.job-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta {
  margin-top: 8px;
}
.elapsed,
.summary {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.spacer {
  flex: 1;
}
.empty {
  padding: 24px 0;
  text-align: center;
  color: var(--el-text-color-secondary);
}
</style>
