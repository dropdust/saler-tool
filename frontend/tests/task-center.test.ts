/**
 * T232 任务中心组件（红→绿）：顶栏徽标 + 任务抽屉（活跃组/最近组/控制/跳转/耗时/空态）。
 * 契约 §5「顶栏入口」「任务抽屉」行。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
  sseUrl: (path: string) => path,
}))

import { api } from '../src/api/client'
import TaskCenter from '../src/components/common/TaskCenter.vue'
import { i18n } from '../src/i18n'
import { useJobCenterStore } from '../src/stores/jobCenter'
import { isAiJobType, jobRoute } from '../src/constants'

const get = vi.mocked(api.get)

function jobRow(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    job_type: 'crawl',
    name: '客户线索挖掘',
    status: 'running',
    progress: {},
    result: null,
    error: null,
    ref_type: 'crawl_job',
    ref_id: 1,
    created_at: '2026-10-14T01:00:00+00:00',
    // 服务端时间戳为朴素 UTC（无时区后缀，如 2026-10-14T05:45:34.74）——按 UTC 解析
    started_at: new Date(Date.now() - 65_000).toISOString().replace('Z', ''),
    finished_at: null,
    can_pause: true,
    rerunnable: true,
    ...overrides,
  }
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/leads/jobs', component: { template: '<div />' } },
      { path: '/content', component: { template: '<div />' } },
    ],
  })
}

async function mountCenter() {
  const router = makeRouter()
  const wrapper = mount(TaskCenter, {
    global: { plugins: [ElementPlus, router, i18n] },
    attachTo: document.body,
  })
  await flushPromises()
  return { wrapper, router, store: useJobCenterStore() }
}

function drawerEl(): HTMLElement {
  return document.body.querySelector('.el-drawer') as HTMLElement
}

beforeEach(() => {
  setActivePinia(createPinia())
  document.body.innerHTML = ''
})

describe('TaskCenter · 顶栏入口', () => {
  it('运行中数量徽标：有活跃任务显示计数，数量为 0 时隐藏', async () => {
    const { store } = await mountCenter()
    // EP badge：hidden（数量 0）时不渲染 sup
    expect(document.body.querySelector('.el-badge__content')).toBeNull()

    store.activeJobs = { 5: jobRow({ id: 5 }) as never, 6: jobRow({ id: 6 }) as never }
    await flushPromises()
    const sup = document.body.querySelector<HTMLElement>('.el-badge__content')!
    expect(sup.textContent).toBe('2')
  })
})

describe('TaskCenter · 任务抽屉', () => {
  it('空态：无任何任务时呈现空提示', async () => {
    const { wrapper } = await mountCenter()
    await wrapper.find('[data-test="task-center-trigger"]').trigger('click')
    await flushPromises()
    expect(drawerEl().textContent).toContain('暂无任务')
  })

  it('活跃组：名称/状态标签/进度文案/已耗时可见', async () => {
    const { wrapper, store } = await mountCenter()
    store.activeJobs = {
      5: jobRow({ id: 5, progress: { total_domains: 4, fetched_domains: 2 } }) as never,
    }
    await wrapper.find('[data-test="task-center-trigger"]').trigger('click')
    await flushPromises()

    const text = drawerEl().textContent ?? ''
    expect(text).toContain('客户线索挖掘')
    expect(text).toContain('抓取：2/4 个域名')
    expect(text).toMatch(/1 分 [4-6] 秒/) // 已耗时（65 秒前启动；毫秒级取整容差）
    expect(drawerEl().querySelector('.el-tag')?.textContent).toBe('执行中')
  })

  it('控制按钮按 can_pause 显隐；can_pause=false 仅有取消', async () => {
    const { wrapper, store } = await mountCenter()
    store.activeJobs = {
      5: jobRow({ id: 5, can_pause: false, job_type: 'backup', name: '创建备份' }) as never,
    }
    await wrapper.find('[data-test="task-center-trigger"]').trigger('click')
    await flushPromises()

    const buttons = [...drawerEl().querySelectorAll('button')].map((b) => b.textContent?.trim())
    expect(buttons).toContain('取消')
    expect(buttons).not.toContain('暂停')
  })

  it('点击暂停调用 store.control(pause)', async () => {
    const { wrapper, store } = await mountCenter()
    store.activeJobs = { 5: jobRow({ id: 5 }) as never }
    const controlSpy = vi.spyOn(store, 'control').mockResolvedValue({ ok: true, status: 'paused' } as never)
    await wrapper.find('[data-test="task-center-trigger"]').trigger('click')
    await flushPromises()

    const pause = [...drawerEl().querySelectorAll('button')].find(
      (b) => b.textContent?.trim() === '暂停',
    )
    pause!.click()
    await flushPromises()
    expect(controlSpy).toHaveBeenCalledWith(5, 'pause')
  })

  it('查看：crawl 任务跳转 /leads/jobs 并关闭抽屉', async () => {
    const { wrapper, router, store } = await mountCenter()
    store.activeJobs = { 5: jobRow({ id: 5 }) as never }
    await wrapper.find('[data-test="task-center-trigger"]').trigger('click')
    await flushPromises()

    const view = [...drawerEl().querySelectorAll('button')].find(
      (b) => b.textContent?.trim() === '查看',
    )
    view!.click()
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/leads/jobs')
  })

  it('最近组：终态结果摘要与状态可见', async () => {
    const { wrapper, store } = await mountCenter()
    store.recentJobs = [
      jobRow({
        id: 3,
        status: 'completed',
        finished_at: '2026-10-14T02:00:00+00:00',
        result: { contacts_created: 7, domains_done: 4 },
      }) as never,
    ]
    await wrapper.find('[data-test="task-center-trigger"]').trigger('click')
    await flushPromises()

    const text = drawerEl().textContent ?? ''
    expect(text).toContain('最近完成')
    expect(text).toContain('联系方式 7')
    expect(text).toContain('完成域名 4')
  })
})

describe('TaskCenter · AI 调用明细入口（T268）', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockResolvedValue({ total: 0, items: [] })
  })

  it('AI 任务卡有「调用明细」，非 AI 任务没有', async () => {
    const { wrapper, store } = await mountCenter()
    store.activeJobs = {
      5: jobRow({ id: 5, job_type: 'ai_seed_expand', name: 'AI 扩充种子' }) as never,
      6: jobRow({ id: 6, job_type: 'crawl' }) as never,
    }
    await wrapper.find('[data-test="task-center-trigger"]').trigger('click')
    await flushPromises()

    const cards = [...drawerEl().querySelectorAll<HTMLElement>('[data-test="active-job"]')]
    const expandCard = cards.find((card) => card.textContent?.includes('AI 扩充种子'))
    const crawlCard = cards.find((card) => card.textContent?.includes('客户线索挖掘'))
    expect(expandCard?.querySelector('[data-test="job-calls"]')?.textContent?.trim()).toBe('调用明细')
    expect(crawlCard?.querySelector('[data-test="job-calls"]')).toBeNull()
  })

  it('最近完成组的 AI 任务同样有入口', async () => {
    const { wrapper, store } = await mountCenter()
    store.recentJobs = [
      jobRow({ id: 9, job_type: 'ai_content_draft', name: 'AI 起草母版', status: 'completed' }) as never,
    ]
    await wrapper.find('[data-test="task-center-trigger"]').trigger('click')
    await flushPromises()

    const card = drawerEl().querySelector<HTMLElement>('[data-test="recent-job"]')
    expect(card?.querySelector('[data-test="job-calls"]')).not.toBeNull()
  })

  it('点击后按任务打开调用明细抽屉：挂在 body 顶层、任务抽屉保持打开', async () => {
    const { wrapper, store } = await mountCenter()
    store.recentJobs = [
      jobRow({ id: 9, job_type: 'ai_seed_expand', name: 'AI 扩充种子', status: 'completed' }) as never,
    ]
    await wrapper.find('[data-test="task-center-trigger"]').trigger('click')
    await flushPromises()

    drawerEl().querySelector<HTMLElement>('[data-test="job-calls"]')!.click()
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/ai/calls', { job_id: 9, limit: 20, offset: 0 })
    const llmDrawer = document.body.querySelector<HTMLElement>('.llm-calls-drawer')
    expect(llmDrawer).not.toBeNull()
    expect(llmDrawer!.textContent).toContain('AI 调用明细')
    // append-to-body：明细抽屉挂在 body 顶层，不属于任务抽屉的子树
    // （否则会被任务抽屉的层叠上下文压住——叠加场景的实际约束）
    expect(document.body.contains(llmDrawer)).toBe(true)
    expect(drawerEl().contains(llmDrawer)).toBe(false)
    // 任务抽屉未被关闭（新入口不做导航）
    expect(drawerEl().textContent).toContain('AI 扩充种子')
  })
})

describe('JOB_TYPE_ROUTES 路由映射', () => {
  it.each([
    ['crawl', '/leads/jobs'],
    ['campaign_send', '/campaigns'],
    ['ai_seed_expand', '/seeds/review'],
    ['ai_content_draft', '/content'],
    ['company_import', '/leads'],
    ['backup', '/settings/backup'],
    ['data_dir_move', '/settings'],
  ])('%s → %s', (jobType, route) => {
    expect(jobRoute(jobType)).toBe(route)
  })

  it('未映射类型回退 null（组件保持抽屉定位）', () => {
    expect(jobRoute('mystery')).toBeNull()
  })

  it('isAiJobType：仅 5 个 AI 任务类型为真（其余任务无 llm_call 明细）', () => {
    const aiTypes = [
      'ai_seed_expand',
      'ai_seed_translate',
      'ai_term_translate',
      'ai_content_draft',
      'ai_content_translate',
    ]
    expect(aiTypes.every((type) => isAiJobType(type))).toBe(true)
    expect(isAiJobType('crawl')).toBe(false)
    expect(isAiJobType('backup')).toBe(false)
  })
})

describe('TaskCenter · 已中断与重跑（T275）', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockResolvedValue({ total: 0, items: [] })
  })

  async function openWithRecent(recent: unknown[]) {
    const { wrapper, store } = await mountCenter()
    store.recentJobs = recent as never
    await wrapper.find('[data-test="task-center-trigger"]').trigger('click')
    await flushPromises()
    return { wrapper, store }
  }

  function cardWith(name: string): HTMLElement {
    return [...drawerEl().querySelectorAll<HTMLElement>('[data-test="recent-job"]')].find((el) =>
      el.textContent?.includes(name),
    )!
  }

  it('按钮显隐矩阵：终态且非 completed 的 rerunnable 才亮出', async () => {
    await openWithRecent([
      jobRow({
        id: 1,
        name: '已中断挖掘',
        status: 'interrupted',
        rerunnable: true,
        finished_at: '2026-10-15T02:00:00',
      }),
      jobRow({
        id: 2,
        name: '已完成挖掘',
        status: 'completed',
        rerunnable: true,
        finished_at: '2026-10-15T02:00:00',
      }),
      jobRow({
        id: 3,
        name: '已中断发送',
        status: 'interrupted',
        job_type: 'campaign_send',
        rerunnable: false,
        finished_at: '2026-10-15T02:00:00',
      }),
      jobRow({
        id: 4,
        name: '失败的备份',
        status: 'failed',
        job_type: 'backup',
        rerunnable: false,
        finished_at: '2026-10-15T02:00:00',
      }),
    ])

    expect(cardWith('已中断挖掘').querySelector('[data-test="job-rerun"]')).not.toBeNull()
    expect(cardWith('已中断挖掘').textContent).toContain('已中断')
    expect(cardWith('已完成挖掘').querySelector('[data-test="job-rerun"]')).toBeNull()
    expect(cardWith('已中断发送').querySelector('[data-test="job-rerun"]')).toBeNull()
    expect(cardWith('失败的备份').querySelector('[data-test="job-rerun"]')).toBeNull()
  })

  it('不可重跑类型的已中断任务给指引文案，可重跑的不给', async () => {
    await openWithRecent([
      jobRow({ id: 1, name: '已中断挖掘', status: 'interrupted', finished_at: '2026-10-15T02:00:00' }),
      jobRow({
        id: 2,
        name: '已中断发送',
        status: 'interrupted',
        job_type: 'campaign_send',
        rerunnable: false,
        finished_at: '2026-10-15T02:00:00',
      }),
    ])

    expect(cardWith('已中断发送').querySelector('[data-test="rerun-guide"]')?.textContent).toContain(
      '请前往相关页面重新发起',
    )
    expect(cardWith('已中断挖掘').querySelector('[data-test="rerun-guide"]')).toBeNull()
  })

  it('点击「重新运行」→ store.rerun(原任务) 并提示已登记', async () => {
    const { store } = await openWithRecent([
      jobRow({
        id: 41,
        name: '已中断挖掘',
        status: 'interrupted',
        finished_at: '2026-10-15T02:00:00',
      }),
    ])
    const rerun = vi.spyOn(store, 'rerun').mockResolvedValue({ job_id: 57 } as never)

    ;(cardWith('已中断挖掘').querySelector('[data-test="job-rerun"]') as HTMLElement).click()
    await flushPromises()

    expect(rerun).toHaveBeenCalledWith(41)
  })

  it('连点两次只发一次请求：在途禁用到回执为止（T277 防抖）', async () => {
    const { store } = await openWithRecent([
      jobRow({
        id: 41,
        name: '已中断挖掘',
        status: 'interrupted',
        finished_at: '2026-10-15T02:00:00',
      }),
    ])
    // 挂起的重跑（回执前按钮必须保持不可再点）——重跑会新建任务，重复点击=重复建单
    let release!: (value: { job_id: number } & Record<string, unknown>) => void
    const gate = new Promise<{ job_id: number } & Record<string, unknown>>((resolve) => {
      release = resolve
    })
    const rerun = vi.spyOn(store, 'rerun').mockReturnValue(gate)

    const btn = cardWith('已中断挖掘').querySelector<HTMLButtonElement>('[data-test="job-rerun"]')!
    btn.click()
    btn.click() // 同一 tick 内连点：此时尚未重渲染（loading 未生效），由组件内在途判定兜住
    await flushPromises()

    expect(rerun).toHaveBeenCalledTimes(1)
    expect(btn.disabled).toBe(true) // 在途禁用（loading ⇒ 原生 disabled）
    btn.click() // 重渲染后再点一次
    await flushPromises()
    expect(rerun).toHaveBeenCalledTimes(1)

    release({ job_id: 57 })
    await flushPromises()
    // 回执后恢复可点：重跑是用户自觉触发的操作，只防连点、不做长冷却
    expect(btn.disabled).toBe(false)
    btn.click()
    await flushPromises()
    expect(rerun).toHaveBeenCalledTimes(2)
  })

  it('守卫失败：不崩（服务端回执由 api 客户端统一提示）', async () => {
    const { store } = await openWithRecent([
      jobRow({
        id: 41,
        name: '已中断挖掘',
        status: 'interrupted',
        finished_at: '2026-10-15T02:00:00',
      }),
    ])
    vi.spyOn(store, 'rerun').mockRejectedValue(new Error('任务已完成，无需重新运行'))

    ;(cardWith('已中断挖掘').querySelector('[data-test="job-rerun"]') as HTMLElement).click()
    await flushPromises()

    expect(cardWith('已中断挖掘')).not.toBeNull() // 抽屉仍在，未因异常中断渲染
  })
})
