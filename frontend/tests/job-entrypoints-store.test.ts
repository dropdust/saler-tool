/**
 * T236 页面级启动点收敛（红→绿）：watchJob 轮询 → store.register + store.waitFor（SSE 驱动）。
 * 代表用例：备份页创建备份 / 种子导入页回灌——启动即登记（任务中心可见、建立订阅），
 * done 事件驱动既有完成逻辑（成功提示与列表/报告刷新）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import { api } from '../src/api/client'
import Backup from '../src/views/settings/Backup.vue'
import SeedsImportExport from '../src/views/seeds/ImportExport.vue'
import { i18n } from '../src/i18n'

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
    id: 9,
    job_type: 'backup',
    name: '创建备份',
    status: 'running',
    progress: { phase: 'copying' },
    result: null,
    error: null,
    ref_type: null,
    ref_id: null,
    created_at: '2026-10-14T01:00:00+00:00',
    started_at: '2026-10-14T01:00:01+00:00',
    finished_at: null,
    can_pause: false,
    rerunnable: false,
    ...overrides,
  }
}

async function mountView(component: unknown, route = '/'): Promise<VueWrapper> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push(route)
  await router.isReady()
  const wrapper = mount(component as never, {
    global: { plugins: [createPinia(), ElementPlus, router, i18n] },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  document.body.innerHTML = ''
})

describe('页面级启动点 · 任务中心收敛', () => {
  it('备份页创建备份：登记进任务中心（建立订阅），done 驱动完成逻辑', async () => {
    let detailCalls = 0
    mockedApi.get.mockImplementation(async (path: string) => {
      if (path === '/backups') return { items: [], total: 0, page: 1, page_size: 20 }
      if (path === '/jobs/9') {
        detailCalls += 1
        return jobRow({
          status: detailCalls === 1 ? 'running' : 'completed',
          result: { path: '/tmp/saler-backup.db' },
        })
      }
      return {}
    })
    mockedApi.post.mockResolvedValueOnce({ job_id: 9 })

    const wrapper = await mountView(Backup)
    const button = wrapper.findAll('button').find((b) => b.text().includes('创建备份'))
    await button!.trigger('click')
    await flushPromises()

    expect(mockedApi.post).toHaveBeenCalledWith('/backups', {})
    expect(FakeEventSource.instances.map((es) => es.url)).toContain('/jobs/9/events')

    const listBefore = mockedApi.get.mock.calls.filter(([p]) => p === '/backups').length
    const es = FakeEventSource.instances.find((item) => item.url === '/jobs/9/events')!
    es.emit('done', { result: { path: '/tmp/saler-backup.db' } })
    await flushPromises()

    const listAfter = mockedApi.get.mock.calls.filter(([p]) => p === '/backups').length
    expect(listAfter).toBeGreaterThan(listBefore) // 完成后刷新备份列表
  })

  it('种子导入页回灌：登记进任务中心，done 后报告落位', async () => {
    let detailCalls = 0
    mockedApi.get.mockImplementation(async (path: string) => {
      if (path === '/graph/nodes') return { items: [], total: 0, page: 1, page_size: 500 }
      if (path === '/jobs/9') {
        detailCalls += 1
        return jobRow({
          job_type: 'ingest_harvest',
          name: '回灌收割结果',
          rerunnable: true,
          status: detailCalls === 1 ? 'running' : 'completed',
          result: { matched: 3, new_domains: 2, dup_domains: 1, unmatched_queries: [] },
        })
      }
      return {}
    })
    mockedApi.post.mockResolvedValueOnce({ job_id: 9 })

    const wrapper = await mountView(SeedsImportExport)
    const pathInput = wrapper
      .findAll('input')
      .find((input) => (input.element as HTMLInputElement).placeholder.includes('绝对路径'))
    await pathInput!.setValue('/tmp/harvest.jsonl')
    const button = wrapper.findAll('button').find((b) => b.text().trim() === '回灌')
    await button!.trigger('click')
    await flushPromises()

    expect(mockedApi.post).toHaveBeenCalledWith('/seeds/ingest', {
      path: '/tmp/harvest.jsonl',
      content: null,
    })
    expect(FakeEventSource.instances.map((es) => es.url)).toContain('/jobs/9/events')

    const es = FakeEventSource.instances.find((item) => item.url === '/jobs/9/events')!
    es.emit('done', { result: { matched: 3, new_domains: 2, dup_domains: 1, unmatched_queries: [] } })
    await flushPromises()

    expect(wrapper.text()).toContain('匹配查询 3')
  })
})
