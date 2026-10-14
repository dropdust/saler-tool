import { api } from './client'
import type { JobPayload } from './types'

export const TERMINAL_STATUSES = ['completed', 'failed', 'cancelled', 'interrupted']

/**
 * 轮询任务直至终态（简单可靠）。
 *
 * @deprecated 005 起以 `stores/jobCenter` 的 `waitFor(jobId)` 为唯一实现（全应用单一
 * 订阅方，页内监控与任务中心同源）；存量调用点随各页面迁移后本函数删除。
 */
export async function watchJob(
  jobId: number,
  onTick?: (job: JobPayload) => void,
  intervalMs = 800,
): Promise<JobPayload> {
  for (;;) {
    const job = await api.get<JobPayload>(`/jobs/${jobId}`)
    onTick?.(job)
    if (TERMINAL_STATUSES.includes(job.status)) return job
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
}
