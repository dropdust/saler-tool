/**
 * T269/T271 迁移（T239）：AI 扩充对话框改由任务中心 store 驱动（register/waitFor + SSE），
 * 保留原行为——任务完成（成功或失败）后「查看调用明细」入口按 job_id 打开 T267 明细抽屉、
 * 不关闭对话框；调用中「已等待」时长随 1s tick 可见。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import { i18n } from '../src/i18n'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
  sseUrl: (path: string) => path,
}))

import { api } from '../src/api/client'
import type { JobPayload } from '../src/api/types'
import { useJobCenterStore } from '../src/stores/jobCenter'
import AiExpandDialog from '../src/views/seeds/AiExpandDialog.vue'

const get = vi.mocked(api.get)
const post = vi.mocked(api.post)

/** 每用例独立 pinia（订阅表为 store 模块级，以 init() 清空重建，防跨用例残留） */
let pinia: Pinia

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

  static find(url: string): FakeEventSource {
    const found = FakeEventSource.instances.find((item) => item.url === url)
    if (!found) throw new Error(`未找到 EventSource：${url}`)
    return found
  }
}

function jobPayload(overrides: Partial<JobPayload> = {}): JobPayload {
  return {
    id: 7,
    job_type: 'ai_seed_expand',
    name: 'AI 扩充种子',
    status: 'completed',
    progress: {},
    result: { nodes_created: 1 },
    error: null,
    ref_type: null,
    ref_id: null,
    created_at: null,
    started_at: null,
    finished_at: null,
    can_pause: false,
    rerunnable: false,
    ...overrides,
  }
}

async function openDialog(pinia: Pinia) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/seeds/review', component: { template: '<div />' } },
    ],
  })
  const wrapper = mount(AiExpandDialog, {
    global: { plugins: [pinia, ElementPlus, router, i18n] },
    attachTo: document.body,
  })
  await flushPromises()
  await (wrapper.vm as unknown as { open: () => Promise<void> }).open()
  await flushPromises()

  const textarea = document.body.querySelector<HTMLTextAreaElement>('.el-textarea__inner')!
  textarea.value = '电力金具出口'
  textarea.dispatchEvent(new Event('input'))
  await flushPromises()
  return wrapper
}

async function clickSubmit() {
  const submit = [...document.body.querySelectorAll<HTMLElement>('button')].find(
    (button) => button.textContent?.trim() === '开始扩充',
  )!
  submit.click()
  await flushPromises()
}

beforeEach(() => {
  document.body.innerHTML = ''
  get.mockReset()
  post.mockReset()
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  get.mockImplementation((path: string) => {
    if (path === '/graph/nodes') {
      return Promise.resolve({ items: [], total: 0, page: 1, page_size: 500 })
    }
    if (path === '/ai/calls') return Promise.resolve({ total: 0, items: [] })
    return Promise.reject(new Error(`unexpected path ${path}`))
  })
  post.mockResolvedValue({ job_id: 7 })
  pinia = createPinia()
  setActivePinia(pinia)
  void useJobCenterStore()
    .init()
    .catch(() => undefined)
})

describe('AiExpandDialog · 查看调用明细入口（T269，store 驱动）', () => {
  it('提交前无入口；成功后出现，点击按 job_id 打开明细且不关闭对话框', async () => {
    let detailCalls = 0
    get.mockImplementation((path: string) => {
      if (path === '/graph/nodes') {
        return Promise.resolve({ items: [], total: 0, page: 1, page_size: 500 })
      }
      if (path === '/ai/calls') return Promise.resolve({ total: 0, items: [] })
      if (path === '/jobs/7') {
        detailCalls += 1
        return Promise.resolve(
          jobPayload({ status: detailCalls === 1 ? 'running' : 'completed' }),
        )
      }
      return Promise.reject(new Error(`unexpected path ${path}`))
    })
    await openDialog(pinia)
    expect(document.body.querySelector('[data-test="expand-view-calls"]')).toBeNull()

    await clickSubmit()
    // 提交即登记：建立既有 /jobs/{id}/events 订阅（唯一订阅方）
    FakeEventSource.find('/jobs/7/events').emit('done', { result: { nodes_created: 1 } })
    await flushPromises()

    const entry = document.body.querySelector<HTMLElement>('[data-test="expand-view-calls"]')
    expect(entry).not.toBeNull()

    entry!.click()
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/ai/calls', { job_id: 7, limit: 20, offset: 0 })
    expect(document.body.querySelector('.llm-calls-drawer')?.textContent).toContain('AI 调用明细')
    // 对话框保持打开（明细叠在其上）
    expect(document.body.querySelector('.el-dialog')?.textContent).toContain('AI 知识图谱扩充')
  })

  it('任务失败后入口仍出现（失败时最需要看明细）', async () => {
    let detailCalls = 0
    get.mockImplementation((path: string) => {
      if (path === '/graph/nodes') {
        return Promise.resolve({ items: [], total: 0, page: 1, page_size: 500 })
      }
      if (path === '/jobs/7') {
        detailCalls += 1
        return Promise.resolve(
          jobPayload({
            status: detailCalls === 1 ? 'running' : 'failed',
            result: null,
            error: 'ProviderError: boom',
          }),
        )
      }
      return Promise.reject(new Error(`unexpected path ${path}`))
    })
    await openDialog(pinia)
    await clickSubmit()
    FakeEventSource.find('/jobs/7/events').emit('error', { code: 'job_failed', message: '任务失败' })
    await flushPromises()
    expect(document.body.querySelector('[data-test="expand-view-calls"]')).not.toBeNull()
  })
})

describe('AiExpandDialog · 调用中「已等待」（T271，store 驱动）', () => {
  it('订阅到 running 时进度文案带已等待时长——前台卡住也知道等了多久', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-15T02:00:24Z'))
    let detailCalls = 0
    get.mockImplementation((path: string) => {
      if (path === '/graph/nodes') {
        return Promise.resolve({ items: [], total: 0, page: 1, page_size: 500 })
      }
      if (path === '/jobs/7') {
        detailCalls += 1
        // 收尾后详情补齐返回终态（真实服务端语义）；首查为 running
        return Promise.resolve(
          jobPayload({ status: detailCalls === 1 ? 'running' : 'completed', result: {} }),
        )
      }
      return Promise.reject(new Error(`unexpected path ${path}`))
    })
    try {
      await openDialog(pinia)
      await clickSubmit()
      FakeEventSource.find('/jobs/7/events').emit('progress', {
        snapshot: jobPayload({
          status: 'running',
          progress: { phase: 'calling_llm' },
          started_at: '2026-10-15T01:59:54.000000',
        }),
      })
      await vi.advanceTimersByTimeAsync(1000)
      const text = document.body.textContent ?? ''
      expect(text).toContain('大模型正在生成候选')
      // tick 前进 1s 后读表：01:59:54 → 02:00:25 = 31s（旧轮询在 emit 时刻即为 30s）
      expect(text).toContain('已等待 31 秒')

      FakeEventSource.find('/jobs/7/events').emit('done', { result: {} }) // 收尾：任务完成
      await flushPromises()
      expect(document.body.textContent).toContain('已完成')
    } finally {
      vi.useRealTimers()
    }
  })
})
