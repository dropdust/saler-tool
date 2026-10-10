import { onBeforeUnmount, ref } from 'vue'
import { sseUrl } from '../api/client'

export interface JobEventHandlers {
  onProgress?: (data: Record<string, unknown>) => void
  onLog?: (data: { level: string; message: string }) => void
  onDone?: (data: Record<string, unknown>) => void
  onError?: (data: Record<string, unknown>) => void
}

/** 订阅任务 SSE 事件（progress / log / done / error），组件卸载自动关闭。 */
export function useJobEvents() {
  const events = ref<Array<{ type: string; data: unknown }>>([])
  let source: EventSource | null = null

  function subscribe(jobId: number, handlers: JobEventHandlers = {}) {
    close()
    source = new EventSource(sseUrl(`/jobs/${jobId}/events`))
    const dispatch = (type: string) => (ev: MessageEvent) => {
      // 原生连接错误事件无 data，忽略（EventSource 自动重连）
      if (!ev.data) return
      let data: Record<string, unknown> = {}
      try {
        data = JSON.parse(ev.data)
      } catch {
        return
      }
      events.value.push({ type, data })
      if (type === 'progress') handlers.onProgress?.(data)
      if (type === 'log') handlers.onLog?.(data as { level: string; message: string })
      if (type === 'done') {
        handlers.onDone?.(data)
        close()
      }
      if (type === 'error') {
        handlers.onError?.(data)
        close()
      }
    }
    source.addEventListener('progress', dispatch('progress'))
    source.addEventListener('log', dispatch('log'))
    source.addEventListener('done', dispatch('done'))
    source.addEventListener('error', dispatch('error'))
  }

  function close() {
    source?.close()
    source = null
  }

  onBeforeUnmount(close)
  return { events, subscribe, close }
}
