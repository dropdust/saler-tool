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

// 结果摘要的中文标签（已知键；未知键忽略，避免把内部字段名直接示人）
const RESULT_LABELS: Record<string, string> = {
  contacts_created: '联系方式',
  domains_found: '域名',
  domains_done: '完成域名',
  seeds_processed: '种子',
  nodes_created: '节点',
  edges_created: '关系',
  seeds_created: '种子',
  created: '新增',
  sent: '已发送',
  processed: '已处理',
}

export interface JobLogLine {
  level: string
  message: string
}

// 订阅表模块级化：EventSource 不进 Pinia 响应式状态
const subscriptions = new Map<number, EventSource>()
// waitFor 的待决收尾表（终态在 _finalize 统一 resolve）
const waiters = new Map<number, (job: JobPayload) => void>()

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
      waiters.get(final.id)?.(final)
      waiters.delete(final.id)
    },

    /** 终态通知挂载点（T244 实现：ElNotification 一次 + 点击跳转）。 */
    // eslint-disable-next-line @typescript-eslint/no-unused-vars -- T244 填充前为占位挂载点
    _onTerminal(_job: JobPayload) {},

    /** 页面启动任务后立即登记：拉一次详情落位并订阅（不等下一次列表刷新）。 */
    async register(jobId: number) {
      try {
        const detail = await api.get<JobPayload>(`/jobs/${jobId}`)
        if (isTerminal(detail.status)) {
          await this._finalize(detail)
          return
        }
        this.activeJobs[jobId] = detail
      } catch {
        /* 详情拉取失败：仍建订阅，由快照补齐 */
      }
      this.ensureSubscribed(jobId)
    },

    /** 任务控制：pause/resume 以服务端回执状态落位；cancel 本地收尾（SSE 迟到经去重不重复）。 */
    async control(jobId: number, action: 'pause' | 'resume' | 'cancel') {
      const resp = await api.post<{ ok: boolean; status: string }>(`/jobs/${jobId}/${action}`)
      const job = this.activeJobs[jobId]
      if (action === 'cancel') {
        this._suppressNotification(jobId)
        await this._finalize({ ...(job as JobPayload), id: jobId, status: 'cancelled' })
        return resp
      }
      if (job && resp?.status) this.activeJobs[jobId] = { ...job, status: resp.status }
      return resp
    },

    /** 等待任务到达终态（取代 watchJob 的 await 语义；终态在 _finalize 统一 resolve）。 */
    async waitFor(jobId: number): Promise<JobPayload> {
      const existing =
        this.activeJobs[jobId] ?? this.recentJobs.find((row) => row.id === jobId) ?? null
      if (existing && isTerminal(existing.status)) return existing
      if (!existing) {
        const detail = await api.get<JobPayload>(`/jobs/${jobId}`)
        if (isTerminal(detail.status)) return detail
        this.activeJobs[jobId] = detail
        this.ensureSubscribed(jobId)
      } else {
        this.ensureSubscribed(jobId)
      }
      return new Promise((resolve) => {
        waiters.set(jobId, resolve)
      })
    },

    /** 该类型的最新活跃任务（对话框重开判定，T239~T241；无则 null）。 */
    activeJobOfType(jobType: string): JobPayload | null {
      const matches = this.activeList.filter((job) => job.job_type === jobType)
      return matches[0] ?? null
    },

    /** 抽屉/页内监控共用的进度视图：百分比或阶段化文案（R8，口径沿用 CrawlJobs）。 */
    progressView(job: JobPayload): { percent: number; text: string; indeterminate: boolean } {
      const p = job.progress ?? {}
      const num = (value: unknown) => (typeof value === 'number' ? value : 0)
      if (job.status === 'completed') return { percent: 100, text: '已完成', indeterminate: false }
      if (job.status === 'failed') return { percent: 100, text: '失败', indeterminate: false }
      if (job.status === 'cancelled') return { percent: 100, text: '已取消', indeterminate: false }
      if (job.status === 'interrupted') return { percent: 100, text: '已中断', indeterminate: false }
      if (num(p.total_seeds)) {
        return {
          percent: Math.min(99, Math.round((num(p.seeds_processed) / num(p.total_seeds)) * 50)),
          text: `检索：${num(p.seeds_processed)}/${num(p.total_seeds)} 条种子`,
          indeterminate: false,
        }
      }
      if (num(p.total_domains)) {
        return {
          percent: Math.min(99, 50 + Math.round((num(p.fetched_domains) / num(p.total_domains)) * 50)),
          text: `抓取：${num(p.fetched_domains)}/${num(p.total_domains)} 个域名`,
          indeterminate: false,
        }
      }
      if (num(p.total) && (typeof p.sent === 'number' || typeof p.done === 'number')) {
        const done = num(p.sent) + num(p.done)
        return {
          percent: Math.min(99, Math.round((done / num(p.total)) * 100)),
          text: `${done}/${num(p.total)}`,
          indeterminate: false,
        }
      }
      if (typeof p.phase === 'string' && p.phase) {
        return { percent: 0, text: `处理中：${p.phase}`, indeterminate: true }
      }
      return {
        percent: job.status === 'running' ? 5 : 0,
        text: '准备中…',
        indeterminate: job.status !== 'running',
      }
    },

    /** 终态结果摘要（抽屉"最近完成"与通知共用）：失败取错误信息，否则取已知结果键。 */
    resultSummary(job: JobPayload): string {
      if (job.status === 'failed') return job.error || '任务失败'
      if (job.status === 'cancelled') return job.error || '已取消'
      if (job.status === 'interrupted') return '应用退出导致中断'
      const result = job.result ?? {}
      const parts: string[] = []
      for (const [key, label] of Object.entries(RESULT_LABELS)) {
        const value = result[key]
        if (typeof value === 'number' && value > 0) parts.push(`${label} ${value}`)
        if (parts.length >= 4) break
      }
      return parts.join(' · ')
    },

    /** 通知抑制挂载点（T244 实现：用户主动取消不通知）。 */
    // eslint-disable-next-line @typescript-eslint/no-unused-vars -- T244 填充前为占位挂载点
    _suppressNotification(_jobId: number) {},
  },
})
