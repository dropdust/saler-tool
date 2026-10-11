/**
 * T183 组件测试（003-seed-language-filter，红阶段）：种子列表语言筛选。
 * 对应 FR-001~008：控件与选项（标准全量 + 库内非标准）、请求携带/清除 lang、
 * 查询复位页码、空态文案（区别于加载失败）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, h, nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus, { ElOption, ElPagination } from 'element-plus'

import { api } from '../src/api/client'
import { LANGS } from '../src/constants'
import { i18n } from '../src/i18n'
import SeedList from '../src/views/seeds/SeedList.vue'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
}))

const mockedApi = vi.mocked(api)

// jsdom 无 ResizeObserver（el-table 依赖）
const g = globalThis as unknown as Record<string, unknown>
if (!g.ResizeObserver) {
  g.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

function seedRow(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    query: 'арматура оптом',
    lang: 'ru',
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
    ...over,
  }
}

function stubApi(routes: Record<string, unknown> = {}) {
  mockedApi.get.mockImplementation(async (path: string) => {
    if (path in routes) return routes[path]
    if (path === '/graph/nodes') return { items: [], total: 0 }
    if (path === '/llm/providers') return []
    if (path === '/seeds/langs') return ['en', 'ru']
    if (path === '/seeds') return { items: [seedRow()], total: 1, page: 1, page_size: 50 }
    return { items: [], total: 0 }
  })
}

async function mountList() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/seeds', component: defineComponent({ render: () => h('div') }) }],
  })
  await router.push('/seeds')
  await router.isReady()
  const wrapper = mount(SeedList, {
    global: { plugins: [createPinia(), router, ElementPlus, i18n] },
  })
  await flushPromises()
  return wrapper
}

function seedsCalls() {
  return mockedApi.get.mock.calls.filter(([path]) => path === '/seeds')
}

function lastSeedsParams(): Record<string, unknown> {
  const calls = seedsCalls()
  return (calls[calls.length - 1]?.[1] ?? {}) as Record<string, unknown>
}

function langSelect(wrapper: VueWrapper): VueWrapper {
  // findComponent 字符串选择器返回 WrapperLike（可能是 DOMWrapper）；此处断言为组件包装器
  return wrapper.findComponent('[data-test="lang-filter"]') as unknown as VueWrapper
}

async function clickQuery(wrapper: VueWrapper) {
  const button = wrapper.findAll('button').find((item) => item.text() === '查询')
  if (!button) throw new Error('未找到"查询"按钮')
  await button.trigger('click')
}

beforeEach(() => {
  vi.clearAllMocks()
  stubApi()
  document.body.innerHTML = ''
})

describe('SeedList 语言筛选（US1）', () => {
  it('渲染"语言"筛选控件（data-test），默认未选择', async () => {
    const wrapper = await mountList()
    expect(langSelect(wrapper).exists()).toBe(true)
    const props = langSelect(wrapper).props() as Record<string, unknown>
    expect(props.modelValue).toBe('')
  })

  it('选项 = 标准语言全量 + 库内非标准取值（标准语言库内无种子亦在列）', async () => {
    stubApi({ '/seeds/langs': ['EN', 'ko'] })
    const wrapper = await mountList()
    const values = langSelect(wrapper)
      .findAllComponents(ElOption)
      .map((option) => option.props('value'))
    for (const item of LANGS) expect(values).toContain(item.code) // 标准全量（含库内暂无种子的语言）
    expect(values).toContain('EN')
    expect(values).toContain('ko')
  })

  it('选择语言并"查询"：请求携带 lang，页码自第 2 页复位为 1', async () => {
    const wrapper = await mountList()

    const pagination = wrapper.findComponent(ElPagination)
    pagination.vm.$emit('update:current-page', 2)
    pagination.vm.$emit('current-change', 2)
    await flushPromises()
    expect(lastSeedsParams().page).toBe(2)

    langSelect(wrapper).vm.$emit('update:modelValue', 'ru')
    await nextTick()
    await clickQuery(wrapper)
    await flushPromises()

    const params = lastSeedsParams()
    expect(params.lang).toBe('ru')
    expect(params.page).toBe(1)
  })

  it('清除语言条件并"查询"：请求不再携带语言限制', async () => {
    const wrapper = await mountList()
    langSelect(wrapper).vm.$emit('update:modelValue', 'ru')
    await nextTick()
    await clickQuery(wrapper)
    await flushPromises()
    expect(lastSeedsParams().lang).toBe('ru')

    langSelect(wrapper).vm.$emit('update:modelValue', '')
    await nextTick()
    await clickQuery(wrapper)
    await flushPromises()
    expect(['', null, undefined]).toContain(lastSeedsParams().lang)
  })

  it('结果为空：显示明确空态文案（区别于加载失败）', async () => {
    stubApi({ '/seeds': { items: [], total: 0, page: 1, page_size: 50 } })
    const wrapper = await mountList()
    expect(wrapper.find('.el-table__empty-text').text()).toContain('没有符合当前筛选条件的种子')
  })
})
