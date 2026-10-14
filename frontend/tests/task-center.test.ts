/**
 * T232 任务中心组件（红→绿）：顶栏徽标 + 任务抽屉（活跃组/最近组/控制/跳转/耗时/空态）。
 * 契约 §5「顶栏入口」「任务抽屉」行。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import TaskCenter from '../src/components/common/TaskCenter.vue'
import { i18n } from '../src/i18n'
import { useJobCenterStore } from '../src/stores/jobCenter'
import { jobRoute } from '../src/constants'

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
})
