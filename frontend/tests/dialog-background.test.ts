/**
 * T238~T241 对话框转后台（005 US2，红→绿）：
 * 任务运行面板三分支（进行中/刚完成/失败）；四个对话框动作（AI 扩充、种子翻译、
 * 内容起草、主题级多语言）的重开呈现进行中态、无重复提交面、关闭后任务登记仍在、
 * 完成后汇总呈现（FR-009/011/012/013；契约 §5「对话框转后台」行）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { i18n } from '../src/i18n'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
  sseUrl: (path: string) => path,
}))

import { api } from '../src/api/client'
import type { JobPayload } from '../src/api/types'
import { useJobCenterStore } from '../src/stores/jobCenter'
import JobRunPanel from '../src/components/common/JobRunPanel.vue'
import AiExpandDialog from '../src/views/seeds/AiExpandDialog.vue'
import AiContentDialog from '../src/views/content/AiContentDialog.vue'
import SeedList from '../src/views/seeds/SeedList.vue'

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
    status: 'running',
    progress: {},
    result: null,
    error: null,
    ref_type: null,
    ref_id: null,
    created_at: '2026-10-16T03:18:00+00:00',
    started_at: '2026-10-16T03:18:00+00:00',
    finished_at: null,
    can_pause: true,
    rerunnable: false,
    ...overrides,
  }
}

function setup(): { pinia: Pinia; router: Router } {
  const pinia = createPinia()
  setActivePinia(pinia)
  // 订阅表为 store 模块级（跨用例残留）：以 init() 清空并重建（等价应用启动，契约 §5「刷新恢复」）
  void useJobCenterStore()
    .init()
    .catch(() => undefined)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/seeds', component: { template: '<div />' } },
      { path: '/seeds/review', component: { template: '<div />' } },
      { path: '/content', component: { template: '<div />' } },
    ],
  })
  return { pinia, router }
}

function bodyButtons(): HTMLElement[] {
  return [...document.body.querySelectorAll<HTMLElement>('button')]
}

function findButton(text: string): HTMLElement | undefined {
  return bodyButtons().find((button) => button.textContent?.trim() === text)
}

// jsdom 无 ResizeObserver（el-table 依赖）
const g = globalThis as unknown as Record<string, unknown>
if (!g.ResizeObserver) {
  g.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

function seedRow() {
  return {
    id: 1,
    query: '电力金具',
    lang: 'zh',
    product_line_id: null,
    persona_id: null,
    market_id: null,
    priority: 2,
    batch: null,
    source_node_id: null,
    template: null,
    status: 'pending',
    source: 'manual',
    confidence: null,
    review_status: 'approved',
    n_candidates: 0,
    n_contacts: 0,
    note: null,
    last_run_at: null,
    created_at: null,
    updated_at: null,
  }
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  mockedApi.get.mockImplementation(async (path: string) => {
    if (path === '/graph/nodes') return { items: [], total: 0, page: 1, page_size: 500 }
    if (path === '/seeds/langs') return ['en', 'ru']
    if (path === '/llm/providers') return [{ id: 1, name: 'on' }]
    if (path === '/seeds') {
      return { items: [seedRow()], total: 1, page: 1, page_size: 50 }
    }
    return { items: [], total: 0, page: 1, page_size: 20 }
  })
  mockedApi.post.mockResolvedValue({ job_id: 7 })
})

describe('JobRunPanel · 三分支（T238）', () => {
  function mountPanel(job: JobPayload, pinia: Pinia): VueWrapper {
    return mount(JobRunPanel, {
      props: { job },
      global: { plugins: [pinia, ElementPlus, i18n] },
    })
  }

  it('进行中：状态/进度/日志尾/取消/常驻提示', () => {
    const { pinia } = setup()
    const store = useJobCenterStore()
    store.activeJobs[7] = jobPayload()
    store.logs[7] = [
      { level: 'info', message: '开始生成候选' },
      { level: 'info', message: '调用大模型…' },
    ]
    const wrapper = mountPanel(
      jobPayload({ progress: { phase: 'calling_llm' }, started_at: '2026-10-16T03:18:00+00:00' }),
      pinia,
    )
    expect(wrapper.find('[data-test="job-run-panel"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('执行中')
    expect(wrapper.text()).toContain('处理中：calling_llm')
    expect(wrapper.find('[data-test="job-run-logs"]').text()).toContain('调用大模型…')
    expect(wrapper.find('[data-test="job-run-cancel"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('关闭本窗口不会中断任务，进度可在任务中心查看')
  })

  it('刚完成：汇总呈现、无取消、无转后台提示', () => {
    const { pinia } = setup()
    const wrapper = mountPanel(
      jobPayload({
        status: 'completed',
        result: { nodes_created: 5, edges_created: 3, seeds_created: 2 },
      }),
      pinia,
    )
    expect(wrapper.text()).toContain('已完成')
    expect(wrapper.text()).toContain('节点 5')
    expect(wrapper.find('[data-test="job-run-cancel"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('关闭本窗口不会中断任务')
  })

  it('失败：错误可见、无取消', () => {
    const { pinia } = setup()
    const wrapper = mountPanel(
      jobPayload({ status: 'failed', error: 'ProviderError: boom' }),
      pinia,
    )
    expect(wrapper.text()).toContain('ProviderError: boom')
    expect(wrapper.find('[data-test="job-run-cancel"]').exists()).toBe(false)
  })

  it('取消：以服务端回执收尾（POST /jobs/{id}/cancel）', async () => {
    const { pinia } = setup()
    const store = useJobCenterStore()
    store.activeJobs[7] = jobPayload()
    mockedApi.post.mockResolvedValueOnce({ ok: true, status: 'cancelled' })
    mockedApi.get.mockImplementation(async (path: string) => {
      if (path === '/jobs/7') return jobPayload({ status: 'cancelled' })
      return { items: [], total: 0, page: 1, page_size: 20 }
    })
    const wrapper = mountPanel(jobPayload(), pinia)
    await wrapper.find('[data-test="job-run-cancel"]').trigger('click')
    await flushPromises()
    expect(mockedApi.post).toHaveBeenCalledWith('/jobs/7/cancel')
  })
})

describe('AiExpandDialog · 重开与转后台（T239）', () => {
  async function mountDialog(pinia: Pinia, router: Router): Promise<VueWrapper> {
    const wrapper = mount(AiExpandDialog, {
      global: { plugins: [pinia, ElementPlus, router, i18n] },
      attachTo: document.body,
    })
    await flushPromises()
    return wrapper
  }

  async function openDialog(wrapper: VueWrapper) {
    await (wrapper.vm as unknown as { open: () => Promise<void> }).open()
    await flushPromises()
  }

  async function submitExpand() {
    const textarea = document.body.querySelector<HTMLTextAreaElement>('.el-textarea__inner')!
    textarea.value = '电力金具出口'
    textarea.dispatchEvent(new Event('input'))
    await flushPromises()
    findButton('开始扩充')!.click()
    await flushPromises()
  }

  it('重开命中进行中任务：呈现运行面板，无表单与「开始扩充」', async () => {
    const { pinia, router } = setup()
    const store = useJobCenterStore()
    store.activeJobs[7] = jobPayload({ progress: { phase: 'calling_llm' } })
    const wrapper = await mountDialog(pinia, router)
    await openDialog(wrapper)

    expect(document.body.querySelector('[data-test="job-run-panel"]')).not.toBeNull()
    expect(document.body.textContent).toContain('关闭本窗口不会中断任务')
    expect(document.body.querySelector('.el-textarea__inner')).toBeNull()
    expect(findButton('开始扩充')).toBeUndefined()
  })

  it('关闭对话框后任务登记仍在（转入后台：store 保留且订阅未断）', async () => {
    const { pinia, router } = setup()
    mockedApi.get.mockImplementation(async (path: string) => {
      if (path === '/jobs/7') return jobPayload()
      if (path === '/graph/nodes') return { items: [], total: 0, page: 1, page_size: 500 }
      return { items: [], total: 0, page: 1, page_size: 20 }
    })
    const wrapper = await mountDialog(pinia, router)
    await openDialog(wrapper)
    await submitExpand()

    const store = useJobCenterStore()
    expect(store.activeJobs[7]).toBeTruthy()
    const es = FakeEventSource.find('/jobs/7/events')

    findButton('关闭')!.click()
    await flushPromises()
    expect(store.activeJobs[7]).toBeTruthy()
    expect(es.closed).toBe(false)
  })

  it('完成时汇总呈现（面板路径）：完成后结果仍可见且可去审核', async () => {
    const { pinia, router } = setup()
    const store = useJobCenterStore()
    const result = { nodes_created: 18, edges_created: 52, seeds_created: 18 }
    store.activeJobs[7] = jobPayload({ progress: { phase: 'calling_llm' } })
    store.ensureSubscribed(7)
    mockedApi.get.mockImplementation(async (path: string) => {
      if (path === '/jobs/7') return jobPayload({ status: 'completed', result, finished_at: '2026-10-16T03:19:40+00:00' })
      if (path === '/graph/nodes') return { items: [], total: 0, page: 1, page_size: 500 }
      return { items: [], total: 0, page: 1, page_size: 20 }
    })
    const wrapper = await mountDialog(pinia, router)
    await openDialog(wrapper)
    expect(document.body.querySelector('[data-test="job-run-panel"]')).not.toBeNull()

    FakeEventSource.find('/jobs/7/events').emit('done', { result })
    await flushPromises()

    expect(document.body.textContent).toContain('新增：节点 18')
    expect(document.body.querySelector('[data-test="expand-view-calls"]')).not.toBeNull()
    expect(findButton('去审核')).toBeDefined()
  })
})

describe('SeedList 翻译对话框 · 重开与完成（T240）', () => {
  /** 行引用必须与 /seeds 响应同一对象：el-table 按引用匹配选行 */
  async function mountList(
    pinia: Pinia,
    router: Router,
    jobDetail?: JobPayload,
  ): Promise<{ wrapper: VueWrapper; row: ReturnType<typeof seedRow> }> {
    const row = seedRow()
    mockedApi.get.mockImplementation(async (path: string) => {
      if (path === '/jobs/9' && jobDetail) return jobDetail
      if (path === '/graph/nodes') return { items: [], total: 0, page: 1, page_size: 500 }
      if (path === '/seeds/langs') return ['en', 'ru']
      if (path === '/llm/providers') return [{ id: 1, name: 'on' }]
      if (path === '/seeds') return { items: [row], total: 1, page: 1, page_size: 50 }
      return { items: [], total: 0, page: 1, page_size: 20 }
    })
    const wrapper = mount(SeedList, {
      global: { plugins: [pinia, router, ElementPlus, i18n] },
      // el-dialog 默认不传送：attachTo 使对话框内容进入 document.body 可查询
      attachTo: document.body,
    })
    await flushPromises()
    return { wrapper, row }
  }

  async function openTranslateDialog(wrapper: VueWrapper, row: ReturnType<typeof seedRow>) {
    // SeedList 组件树不在 document.body（未 attachTo）：工具栏按钮从 wrapper 内查找
    const table = wrapper.findComponent({ name: 'ElTable' })
    table.vm.toggleRowSelection(row, true)
    await flushPromises()
    const trigger = wrapper
      .findAll('button')
      .find((button) => button.text().trim() === '翻译选中（1）')
    if (!trigger) throw new Error('未选中行（翻译选中（1）按钮未出现）')
    await trigger.trigger('click')
    await flushPromises()
  }

  it('重开命中进行中翻译任务：呈现运行面板，无「开始翻译」提交面', async () => {
    const { pinia, router } = setup()
    const store = useJobCenterStore()
    store.activeJobs[9] = jobPayload({
      id: 9,
      job_type: 'ai_seed_translate',
      name: 'AI 翻译种子',
    })
    const { wrapper, row } = await mountList(pinia, router)
    await openTranslateDialog(wrapper, row)

    expect(document.body.querySelector('[data-test="job-run-panel"]')).not.toBeNull()
    expect(document.body.textContent).toContain('关闭本窗口不会中断任务')
    expect(findButton('开始翻译')).toBeUndefined()
  })

  it('重开等待至完成：关闭对话框并刷新种子列表', async () => {
    const { pinia, router } = setup()
    const store = useJobCenterStore()
    store.activeJobs[9] = jobPayload({
      id: 9,
      job_type: 'ai_seed_translate',
      name: 'AI 翻译种子',
    })
    store.ensureSubscribed(9)
    const { wrapper, row } = await mountList(
      pinia,
      router,
      jobPayload({
        id: 9,
        job_type: 'ai_seed_translate',
        status: 'completed',
        result: { created: 3 },
        finished_at: '2026-10-16T03:19:40+00:00',
      }),
    )
    await openTranslateDialog(wrapper, row)
    const seedsBefore = mockedApi.get.mock.calls.filter(([path]) => path === '/seeds').length

    FakeEventSource.find('/jobs/9/events').emit('done', { result: { created: 3 } })
    await flushPromises()

    const seedsAfter = mockedApi.get.mock.calls.filter(([path]) => path === '/seeds').length
    expect(seedsAfter).toBeGreaterThan(seedsBefore)
  })
})

describe('AiContentDialog · 两动作重开（T241）', () => {
  function mountContent(pinia: Pinia, router: Router): VueWrapper {
    return mount(AiContentDialog, {
      global: { plugins: [pinia, ElementPlus, router, i18n] },
      attachTo: document.body,
    })
  }

  it('起草动作命中进行中任务：draft 页呈现运行面板，无「开始起草」', async () => {
    const { pinia, router } = setup()
    const store = useJobCenterStore()
    store.activeJobs[11] = jobPayload({
      id: 11,
      job_type: 'ai_content_draft',
      name: 'AI 内容起草',
    })
    const wrapper = mountContent(pinia, router)
    ;(wrapper.vm as unknown as { open: (t: { id: number; name: string; master_lang: string }) => void }).open(
      { id: 1, name: '主题A', master_lang: 'zh' },
    )
    await flushPromises()

    expect(document.body.querySelector('[data-test="job-run-panel"]')).not.toBeNull()
    expect(findButton('开始起草')).toBeUndefined()
  })

  it('多语言动作命中进行中任务：translate 页呈现运行面板，无「开始生成」', async () => {
    const { pinia, router } = setup()
    const store = useJobCenterStore()
    store.activeJobs[12] = jobPayload({
      id: 12,
      job_type: 'ai_content_translate',
      name: 'AI 内容翻译',
    })
    const wrapper = mountContent(pinia, router)
    ;(wrapper.vm as unknown as { open: (t: { id: number; name: string; master_lang: string }) => void }).open(
      { id: 1, name: '主题A', master_lang: 'zh' },
    )
    await flushPromises()

    expect(document.body.querySelector('[data-test="job-run-panel"]')).not.toBeNull()
    expect(findButton('开始生成')).toBeUndefined()
  })
})
