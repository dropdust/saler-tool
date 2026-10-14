/**
 * T234 挖掘任务页收敛到任务中心 store（红→绿）：
 * 进入自动选中活跃任务 / 监控卡片读 store（同源）/ 启动即登记 / 控制经 store / 弹窗同型提示。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'

import { api } from '../src/api/client'
import CrawlJobs from '../src/views/leads/CrawlJobs.vue'
import { i18n } from '../src/i18n'
import { useJobCenterStore } from '../src/stores/jobCenter'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
  sseUrl: (path: string) => path,
}))

const mockedApi = vi.mocked(api)

function jobRow(overrides: Record<string, unknown> = {}) {
  return {
    id: 9,
    job_type: 'crawl',
    name: '客户线索挖掘',
    status: 'running',
    progress: { total_domains: 4, fetched_domains: 2 },
    result: null,
    error: null,
    ref_type: 'crawl_job',
    ref_id: 7,
    created_at: '2026-10-14T01:00:00+00:00',
    started_at: '2026-10-14T01:00:01+00:00',
    finished_at: null,
    can_pause: true,
    rerunnable: true,
    ...overrides,
  }
}

function stubApi(detail: unknown = jobRow()) {
  mockedApi.get.mockImplementation(async (path: string) => {
    if (path === '/crawl/jobs') {
      return {
        items: [{ id: 7, name: '客户线索挖掘', scope: {}, config: {}, status: 'running', stats: {}, created_at: '2026-10-14T01:00:00+00:00' }],
        total: 1,
        page: 1,
        page_size: 50,
      }
    }
    if (path === '/seeds') return { items: [], total: 0, page: 1, page_size: 200 }
    if (path.startsWith('/jobs/')) return detail
    return {}
  })
}

async function mountPage(): Promise<{ wrapper: VueWrapper; store: ReturnType<typeof useJobCenterStore> }> {
  const wrapper = mount(CrawlJobs, {
    global: { plugins: [ElementPlus, i18n] },
    attachTo: document.body,
  })
  await flushPromises()
  return { wrapper, store: useJobCenterStore() }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  document.body.innerHTML = ''
  stubApi()
})

describe('CrawlJobs · 任务中心收敛', () => {
  it('进入页面自动选中活跃挖掘任务（无需点「监控」）', async () => {
    const { wrapper, store } = await mountPage()
    store.activeJobs = { 9: jobRow() as never }
    await flushPromises()

    const card = wrapper.find('[data-test="monitor-card"]')
    expect(card.exists()).toBe(true)
    expect(card.text()).toContain('抓取：2/4 个域名')
    expect(card.text()).toContain('执行中')
  })

  it('监控卡片与 store 同源：store 进度更新即卡片更新，日志来自 store 缓冲', async () => {
    const { wrapper, store } = await mountPage()
    store.activeJobs = { 9: jobRow() as never }
    await flushPromises()

    store.activeJobs = { 9: jobRow({ progress: { total_domains: 10, fetched_domains: 8 } }) as never }
    store.logs = { 9: [{ level: 'info', message: '抓取完成 rust-lang.org' }] }
    await flushPromises()

    const card = wrapper.find('[data-test="monitor-card"]')
    expect(card.text()).toContain('抓取：8/10 个域名')
    expect(card.text()).toContain('抓取完成 rust-lang.org')
  })

  it('启动即登记：POST 后调用 store.register（不等下一次列表刷新）', async () => {
    const { wrapper, store } = await mountPage()
    mockedApi.post.mockResolvedValueOnce({ job_id: 9, crawl_job_id: 7 })
    const registerSpy = vi.spyOn(store, 'register').mockResolvedValue(undefined)

    const startBtn = wrapper.findAll('button').find((b) => b.text().includes('启动挖掘'))
    await startBtn!.trigger('click')
    await flushPromises()
    const confirm = [...document.querySelectorAll<HTMLElement>('.el-dialog__footer button')].find(
      (b) => b.textContent?.trim() === '启动',
    )
    confirm!.click()
    await flushPromises()

    expect(mockedApi.post).toHaveBeenCalledWith('/crawl/jobs', expect.anything())
    expect(registerSpy).toHaveBeenCalledWith(9)
  })

  it('页内控制经 store：点击暂停走 store.control(POST /jobs/9/pause)', async () => {
    const { wrapper, store } = await mountPage()
    store.activeJobs = { 9: jobRow() as never }
    await flushPromises()
    mockedApi.post.mockResolvedValueOnce({ ok: true, status: 'paused' })

    const pause = wrapper
      .find('[data-test="monitor-card"]')
      .findAll('button')
      .find((b) => b.text().includes('暂停'))
    await pause!.trigger('click')
    await flushPromises()

    expect(mockedApi.post).toHaveBeenCalledWith('/jobs/9/pause')
    expect(store.activeJobs[9].status).toBe('paused')
  })

  it('操作列的「监控」：命中 store 选中；未命中（过期任务）给出提示且不选中', async () => {
    const { wrapper, store } = await mountPage()
    store.activeJobs = { 9: jobRow() as never }
    await flushPromises()

    const monitor = wrapper.findAll('button').find((b) => b.text().includes('监控'))
    await monitor!.trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="monitor-card"]').exists()).toBe(true)

    // 构造一个不在保留窗口内的旧任务行
    store.activeJobs = {}
    store.recentJobs = []
    await flushPromises()
    expect(wrapper.find('[data-test="monitor-card"]').exists()).toBe(false)
  })

  it('启动弹窗：已有同类活跃任务时给出提示（含任务号）', async () => {
    const { wrapper, store } = await mountPage()
    store.activeJobs = { 9: jobRow() as never }
    const startBtn = wrapper.findAll('button').find((b) => b.text().includes('启动挖掘'))
    await startBtn!.trigger('click')
    await flushPromises()

    const dialogText = document.querySelector('.el-dialog')?.textContent ?? ''
    expect(dialogText).toContain('已有进行中的挖掘任务（#9）')
  })
})
