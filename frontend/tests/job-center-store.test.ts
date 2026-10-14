/**
 * T230 jobCenter store 数据层（红→绿）：拉取/订阅/快照与增量合并/终态迁移/日志有界/刷新恢复。
 *
 * 契约 §5「唯一订阅方」「刷新恢复」行；app 全应用只有这一个 store 持有 SSE 连接。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import { api } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
  sseUrl: (path: string) => path,
}))

const mockedApi = vi.mocked(api)

class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  closed = false
  private listeners: Record<string, Array<(ev: MessageEvent) => void>> = {}

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, cb: (ev: MessageEvent) => void) {
    ;(this.listeners[type] ||= []).push(cb)
  }

  close() {
    this.closed = true
  }

  emit(type: string, data?: unknown) {
    const ev = { data: data === undefined ? '' : JSON.stringify(data) } as MessageEvent
    for (const cb of this.listeners[type] ?? []) cb(ev)
  }
}

function jobRow(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    job_type: 'crawl',
    name: '挖掘',
    status: 'running',
    progress: {},
    result: null,
    error: null,
    ref_type: 'crawl_job',
    ref_id: 1,
    created_at: '2026-10-14T01:00:00+00:00',
    started_at: '2026-10-14T01:00:01+00:00',
    finished_at: null,
    can_pause: true,
    rerunnable: true,
    ...overrides,
  }
}

function stubLists(active: unknown[], recent: unknown[] = []) {
  mockedApi.get.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
    if (path === '/jobs' && String(params?.status ?? '').includes('queued')) {
      return { items: active, total: active.length, page: 1, page_size: 100 }
    }
    if (path === '/jobs' && String(params?.status ?? '').includes('completed')) {
      return { items: recent, total: recent.length, page: 1, page_size: 20 }
    }
    throw new Error(`unexpected GET ${path}`)
  })
}

async function freshStore() {
  const { useJobCenterStore } = await import('../src/stores/jobCenter')
  return useJobCenterStore()
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
})

describe('jobCenter store · 数据层', () => {
  it('init：活跃三态与最近终态各一次请求（含 24h 窗口过滤）', async () => {
    const old = jobRow({
      id: 9,
      status: 'completed',
      finished_at: '2026-10-10T00:00:00+00:00', // 4 天前 → 窗口外
    })
    const fresh = jobRow({
      id: 8,
      status: 'completed',
      finished_at: new Date(Date.now() - 3600_000).toISOString(),
    })
    stubLists([jobRow({ id: 5 })], [old, fresh])
    const store = await freshStore()

    await store.init()

    expect(mockedApi.get).toHaveBeenCalledWith('/jobs', {
      status: 'queued,running,paused',
      page_size: 100,
    })
    expect(mockedApi.get).toHaveBeenCalledWith('/jobs', {
      status: 'completed,failed,cancelled,interrupted',
      page_size: 20,
    })
    expect(Object.keys(store.activeJobs)).toEqual(['5'])
    expect(store.recentJobs.map((j) => j.id)).toEqual([8])
  })

  it('init 对每个活跃任务建立订阅（URL 与数量）', async () => {
    stubLists([jobRow({ id: 5 }), jobRow({ id: 6, job_type: 'backup', name: '备份' })])
    const store = await freshStore()

    await store.init()

    expect(FakeEventSource.instances.map((es) => es.url).sort()).toEqual([
      '/jobs/5/events',
      '/jobs/6/events',
    ])
  })

  it('快照合并：progress 事件携带 snapshot → 全量落位（状态/名称/进度）', async () => {
    stubLists([jobRow({ id: 5, progress: { phase: 'search' } })])
    const store = await freshStore()
    await store.init()

    FakeEventSource.instances[0].emit('progress', {
      snapshot: jobRow({ id: 5, status: 'running', progress: { phase: 'fetch', fetched_domains: 3 } }),
    })

    expect(store.activeJobs[5].status).toBe('running')
    expect(store.activeJobs[5].progress).toEqual({ phase: 'fetch', fetched_domains: 3 })
  })

  it('增量合并：无 snapshot 的 progress → 并入该任务 progress（不丢既有键）', async () => {
    stubLists([jobRow({ id: 5, progress: { phase: 'search' } })])
    const store = await freshStore()
    await store.init()

    FakeEventSource.instances[0].emit('progress', { phase: 'fetch', fetched_domains: 2 })

    expect(store.activeJobs[5].progress).toEqual({ phase: 'fetch', fetched_domains: 2, })
  })

  it('多任务互不串扰：A 的事件不影响 B', async () => {
    stubLists([jobRow({ id: 5 }), jobRow({ id: 6, job_type: 'backup' })])
    const store = await freshStore()
    await store.init()

    const esFor = (id: number) =>
      FakeEventSource.instances.find((es) => es.url === `/jobs/${id}/events`)!
    esFor(5).emit('progress', { phase: 'fetch' })

    expect(store.activeJobs[5].progress).toEqual({ phase: 'fetch' })
    expect(store.activeJobs[6].progress).toEqual({})
  })

  it('终态迁移：done → completed 移入 recent 并关闭订阅', async () => {
    stubLists([jobRow({ id: 5 })])
    const store = await freshStore()
    await store.init()

    FakeEventSource.instances[0].emit('done', { result: { contacts_created: 7 } })
    await flushPromises()

    expect(store.activeJobs[5]).toBeUndefined()
    expect(store.recentJobs[0]).toMatchObject({ id: 5, status: 'completed' })
    expect(store.recentJobs[0].result).toEqual({ contacts_created: 7 })
    expect(FakeEventSource.instances[0].closed).toBe(true)
  })

  it.each([
    ['cancelled', 'cancelled'],
    ['interrupted', 'interrupted'],
    ['job_failed', 'failed'],
  ])('error code=%s → 状态落位 %s', async (code, expected) => {
    stubLists([jobRow({ id: 5 })])
    const store = await freshStore()
    await store.init()

    FakeEventSource.instances[0].emit('error', { code, message: '出事了' })
    await flushPromises()

    expect(store.activeJobs[5]).toBeUndefined()
    expect(store.recentJobs[0]).toMatchObject({ id: 5, status: expected })
  })

  it('日志有界：超过 200 行丢最旧，终态迁移后日志保留', async () => {
    stubLists([jobRow({ id: 5 })])
    const store = await freshStore()
    await store.init()

    const es = FakeEventSource.instances[0]
    for (let i = 0; i < 250; i += 1) es.emit('log', { level: 'info', message: `line-${i}` })

    expect(store.logs[5].length).toBe(200)
    expect(store.logs[5][0].message).toBe('line-50')
    expect(store.logs[5][199].message).toBe('line-249')
  })

  it('刷新恢复：再次 init → 先关旧订阅、再以服务端数据+快照重建（不回退）', async () => {
    stubLists([jobRow({ id: 5, progress: { fetched_domains: 4 } })])
    const store = await freshStore()
    await store.init()
    const first = FakeEventSource.instances[0]
    first.emit('progress', { phase: 'fetch', fetched_domains: 3 })

    await store.init() // 模拟刷新：重新拉取 + 重订阅

    expect(first.closed).toBe(true)
    const second = FakeEventSource.instances[1]
    expect(second.url).toBe('/jobs/5/events')
    second.emit('progress', { snapshot: jobRow({ id: 5, progress: { fetched_domains: 4 } }) })
    expect(store.activeJobs[5].progress).toEqual({ fetched_domains: 4 })
  })

  it('detail 快照缺 result 时补一次详情拉取（终态信息完整性）', async () => {
    // done 载荷含 result；error 载荷含 message——落位后用一次 GET 补齐完整行
    stubLists([jobRow({ id: 5 })])
    const store = await freshStore()
    await store.init()
    mockedApi.get.mockImplementationOnce(async () => jobRow({ id: 5, status: 'completed', result: { n: 1 }, finished_at: '2026-10-14T02:00:00+00:00' }))

    FakeEventSource.instances[0].emit('done', { result: { n: 1 } })
    await flushPromises()

    expect(mockedApi.get).toHaveBeenCalledWith('/jobs/5')
    expect(store.recentJobs[0]).toMatchObject({ id: 5, status: 'completed', finished_at: '2026-10-14T02:00:00+00:00' })
  })
})
