/**
 * T235 计划监控页收敛到任务中心 store（红→绿）：
 * 自动选中活跃发送 / 实时统计读 store / 控制后同步 store / 终态刷新计划与列表。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import { api } from '../src/api/client'
import CampaignMonitor from '../src/views/campaigns/CampaignMonitor.vue'
import { i18n } from '../src/i18n'
import { useJobCenterStore } from '../src/stores/jobCenter'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
  sseUrl: (path: string) => path,
}))

const mockedApi = vi.mocked(api)

function campaignRow(overrides: Record<string, unknown> = {}) {
  return {
    id: 3,
    name: '秋季推广',
    status: 'running',
    channels: [],
    rounds: [],
    stats: { planned: 10, sent: 3 },
    active_job_id: 9,
    created_at: '2026-10-14T01:00:00+00:00',
    ...overrides,
  }
}

function sendJob(overrides: Record<string, unknown> = {}) {
  return {
    id: 9,
    job_type: 'campaign_send',
    name: '发送计划：秋季推广',
    status: 'running',
    progress: { total: 10, sent: 3, failed: 1, bounced: 1, skipped: 0, suppressed: 0, remaining: 5 },
    result: null,
    error: null,
    ref_type: 'campaign',
    ref_id: 3,
    created_at: '2026-10-14T01:00:00+00:00',
    started_at: '2026-10-14T01:00:01+00:00',
    finished_at: null,
    can_pause: true,
    rerunnable: false,
    ...overrides,
  }
}

function stubApi() {
  mockedApi.get.mockImplementation(async (path: string) => {
    if (path === '/campaigns') return [campaignRow()]
    if (path === '/campaigns/3') return campaignRow()
    if (path === '/jobs/9') return sendJob()
    return {}
  })
}

async function mountPage(): Promise<{ wrapper: VueWrapper; store: ReturnType<typeof useJobCenterStore> }> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(CampaignMonitor, {
    global: { plugins: [ElementPlus, router, i18n] },
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

describe('CampaignMonitor · 任务中心收敛', () => {
  it('进入页面自动选中活跃发送计划（无需点选行）', async () => {
    const { wrapper, store } = await mountPage()
    store.activeJobs = { 9: sendJob() as never }
    await flushPromises()

    const card = wrapper.find('.monitor')
    expect(card.exists()).toBe(true)
    expect(card.text()).toContain('秋季推广')
  })

  it('实时统计读 store progress（已发/失败/退信随 store 更新）', async () => {
    const { wrapper, store } = await mountPage()
    store.activeJobs = { 9: sendJob() as never }
    await flushPromises()

    let live = wrapper.find('.live')
    expect(live.text()).toContain('已发 3')
    expect(live.text()).toContain('失败 1')

    store.activeJobs = {
      9: sendJob({ progress: { total: 10, sent: 8, failed: 1, bounced: 1, skipped: 0, suppressed: 0, remaining: 0 } }) as never,
    }
    await flushPromises()
    live = wrapper.find('.live')
    expect(live.text()).toContain('已发 8')
  })

  it('控制（暂停）后同步 store：refresh 拉 /jobs/9 并以回执状态落位', async () => {
    const { wrapper, store } = await mountPage()
    store.activeJobs = { 9: sendJob() as never }
    await flushPromises()
    mockedApi.post.mockResolvedValueOnce({ ok: true })
    mockedApi.get.mockImplementation(async (path: string) => {
      if (path === '/campaigns') return [campaignRow({ status: 'paused' })]
      if (path === '/campaigns/3') return campaignRow({ status: 'paused' })
      if (path === '/jobs/9') return sendJob({ status: 'paused' })
      return {}
    })

    const rowPause = wrapper.findAll('button').find((b) => b.text().includes('暂停'))
    await rowPause!.trigger('click')
    await flushPromises()

    expect(mockedApi.post).toHaveBeenCalledWith('/campaigns/3/pause')
    expect(mockedApi.get).toHaveBeenCalledWith('/jobs/9')
    expect(store.activeJobs[9].status).toBe('paused')
  })

  it('store 中任务到达终态 → 自动刷新计划详情与列表', async () => {
    const { store } = await mountPage()
    store.activeJobs = { 9: sendJob() as never }
    await flushPromises()
    mockedApi.get.mockClear()

    store.activeJobs = {} // 模拟 store 收尾迁移（终态不再出现在 active）
    store.recentJobs = [sendJob({ status: 'completed', finished_at: '2026-10-14T02:00:00+00:00' }) as never]
    await flushPromises()

    const paths = mockedApi.get.mock.calls.map(([path]) => path)
    expect(paths).toContain('/campaigns/3')
    expect(paths).toContain('/campaigns')
  })
})
