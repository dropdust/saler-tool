/**
 * 全局任务中心 store（005）——全应用唯一 SSE 订阅方与任务状态单一事实源。
 *
 * - `init()` 拉取活跃（queued/running/paused）与最近终态（24h 窗口，≤20 条），
 *   对每个活跃任务订阅既有 `/jobs/{id}/events`（快照先行、终态即断）；刷新/重进
 *   应用即自动恢复展示，无需手动"监控"（契约 §5「刷新恢复」）。
 * - 事件合并：progress 快照全量落位 / 增量并入 progress；log 有界缓冲（≤200 行）；
 *   done/error 落位终态并迁移 active→recent，随后 best-effort 拉一次详情补齐
 *   finished_at/result（事件载荷已足够展示，详情失败不阻断）。
 * - EventSource 与订阅表置于模块级（非响应式），组件与页内监控一律读本 store——
 *   同一任务全应用一份连接、一处状态（FR-008 同源一致的实现基础）。
 */

import { defineStore } from 'pinia'

import { api, sseUrl } from '../api/client'
import { TERMINAL_STATUSES } from '../api/jobs'
import type { JobPayload } from '../api/types'

export const ACTIVE_STATUSES = ['queued', 'running', 'paused']
const RECENT_STATUSES = ['completed', 'failed', 'cancelled', 'interrupted']
const RECENT_WINDOW_MS = 24 * 60 * 60 * 1000
const RECENT_LIMIT = 20
const LOG_LIMIT = 200

export interface JobLogLine {
  level: string
  message: string
}

// 订阅表模块级化：EventSource 不进 Pinia 响应式状态
const subscriptions = new Map<number, EventSource>()

function closeAllSubscriptions() {
  for (const source of subscriptions.values()) source.close()
  subscriptions.clear()
}

function isTerminal(status: string | null | undefined): boolean {
  return !!status && TERMINAL_STATUSES.includes(status)
}

export const useJobCenterStore = defineStore('jobCenter', {
  state: () => ({
    activeJobs: {} as Record<number, JobPayload>,
    recentJobs: [] as JobPayload[],
    logs: {} as Record<number, JobLogLine[]>,
  }),

  getters: {
    /** 活跃任务（含排队与暂停），新→旧。 */
    activeList(state): JobPayload[] {
      return Object.values(state.activeJobs).sort((a, b) => b.id - a.id)
    },
    /** 顶栏徽标计数：全部未结束任务。 */
    activeCount(state): number {
      return Object.keys(state.activeJobs).length
    },
  },

  actions: {
    /** 应用启动/刷新入口：重建全部状态与订阅（幂等，先关旧订阅）。 */
    async init() {
      closeAllSubscriptions()
      this.activeJobs = {}
      this.logs = {}
      const [active, recent] = await Promise.all([
        api.get<{ items: JobPayload[] }>('/jobs', {
          status: ACTIVE_STATUSES.join(','),
          page_size: 100,
        }),
        api.get<{ items: JobPayload[] }>('/jobs', {
          status: RECENT_STATUSES.join(','),
          page_size: RECENT_LIMIT,
        }),
      ])
      for (const job of active.items) {
        this.activeJobs[job.id] = job
        this.ensureSubscribed(job.id)
      }
      const cutoff = Date.now() - RECENT_WINDOW_MS
      this.recentJobs = recent.items
        .filter((job) => !job.finished_at || Date.parse(job.finished_at) >= cutoff)
        .slice(0, RECENT_LIMIT)
    },

    /** 为任务建立 SSE 订阅（已订阅则幂等跳过）；EventSource 原生断线自动重连。 */
    ensureSubscribed(jobId: number) {
      if (subscriptions.has(jobId)) return
      const source = new EventSource(sseUrl(`/jobs/${jobId}/events`))
      subscriptions.set(jobId, source)
      const dispatch = (type: string) => (ev: MessageEvent) => this._handleEvent(jobId, type, ev)
      source.addEventListener('progress', dispatch('progress'))
      source.addEventListener('log', dispatch('log'))
      source.addEventListener('done', dispatch('done'))
      source.addEventListener('error', dispatch('error'))
    },

    _handleEvent(jobId: number, type: string, ev: MessageEvent) {
      // 原生连接错误事件无 data，忽略（EventSource 自动重连）
      if (!ev.data) return
      let data: Record<string, unknown>
      try {
        data = JSON.parse(ev.data)
      } catch {
        return
      }
      const job = this.activeJobs[jobId]

      if (type === 'progress') {
        if (data.snapshot) {
          const snapshot = data.snapshot as JobPayload
          if (isTerminal(snapshot.status)) {
            void this._finalize(snapshot)
            return
          }
          this.activeJobs[jobId] = { ...(job as JobPayload), ...snapshot }
        } else if (job) {
          this.activeJobs[jobId] = { ...job, progress: { ...job.progress, ...data } }
        }
        return
      }

      if (type === 'log') {
        const lines = this.logs[jobId] ?? []
        lines.push({ level: String(data.level ?? 'info'), message: String(data.message ?? '') })
        this.logs[jobId] = lines.slice(-LOG_LIMIT)
        return
      }

      if (type === 'done') {
        // 运行时 done 载荷={result}；终态订阅（快照路径）载荷=完整 JobPayload
        const merged = { ...(job as JobPayload), ...data, id: jobId } as JobPayload
        if (!merged.status || !isTerminal(merged.status)) merged.status = 'completed'
        void this._finalize(merged)
        return
      }

      if (type === 'error') {
        const code = String(data.code ?? 'job_failed')
        const status = code === 'cancelled' ? 'cancelled' : code === 'interrupted' ? 'interrupted' : 'failed'
        void this._finalize({
          ...(job as JobPayload),
          id: jobId,
          status,
          error: String(data.message ?? (job?.error ?? '')),
        })
      }
    },

    /** 终态收尾：关闭订阅、active→recent 迁移、best-effort 补齐详情、通知挂载点。 */
    async _finalize(job: JobPayload) {
      subscriptions.get(job.id)?.close()
      subscriptions.delete(job.id)
      delete this.activeJobs[job.id]

      let final: JobPayload = {
        ...job,
        finished_at: job.finished_at ?? new Date().toISOString(),
      }
      try {
        final = { ...final, ...(await api.get<JobPayload>(`/jobs/${job.id}`)) }
      } catch {
        /* 详情补齐失败：保留事件载荷（展示已足够） */
      }

      this.recentJobs = [final, ...this.recentJobs.filter((row) => row.id !== final.id)].slice(
        0,
        RECENT_LIMIT,
      )
      this._onTerminal(final)
    },

    /** 终态通知挂载点（T244 实现：ElNotification 一次 + 点击跳转）。 */
    // eslint-disable-next-line @typescript-eslint/no-unused-vars -- T244 填充前为占位挂载点
    _onTerminal(_job: JobPayload) {},
  },
})
