import { api } from './client'
import type { JobPayload } from './types'

export const TERMINAL_STATUSES = ['completed', 'failed', 'cancelled']

/**
 * 轮询任务直至终态（简单可靠）。
 * 需要流式进度的场景（长时间挖掘/发送）用 `composables/useJobEvents` 的 SSE。
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
