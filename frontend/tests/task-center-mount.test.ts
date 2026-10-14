/**
 * T233 MainLayout 挂载（红→绿）：任务中心入口常驻顶栏 + 应用启动即 init（刷新恢复接线）。
 * 契约 §5「顶栏入口」「刷新恢复」行。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import { api } from '../src/api/client'
import MainLayout from '../src/layouts/MainLayout.vue'
import { i18n } from '../src/i18n'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
  sseUrl: (path: string) => path,
}))

const mockedApi = vi.mocked(api)

async function mountLayout() {
  const pinia = createPinia()
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: defineComponent({ render: () => h('div') }), meta: { title: '总览' } },
    ],
  })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(MainLayout, {
    global: { plugins: [pinia, router, ElementPlus, i18n] },
    attachTo: document.body,
  })
  await flushPromises()
  return { wrapper }
}

beforeEach(() => {
  vi.clearAllMocks()
  document.body.innerHTML = ''
  mockedApi.get.mockImplementation(async (path: string) =>
    path === '/jobs' ? { items: [], total: 0, page: 1, page_size: 100 } : {},
  )
})

describe('MainLayout · 任务中心接线', () => {
  it('顶栏常驻任务中心入口', async () => {
    await mountLayout()
    expect(document.body.querySelector('[data-test="task-center-trigger"]')).toBeTruthy()
  })

  it('应用启动即 init：拉取活跃与最近终态两个列表（刷新恢复，0 手动操作）', async () => {
    await mountLayout()
    const calls = mockedApi.get.mock.calls.map(([path, params]) => [path, params])
    expect(calls).toContainEqual([
      '/jobs',
      { status: 'queued,running,paused', page_size: 100 },
    ])
    expect(calls).toContainEqual([
      '/jobs',
      { status: 'completed,failed,cancelled,interrupted', page_size: 20 },
    ])
  })
})
