/**
 * T198 组件/纯函数测试：图谱视图批次筛选下拉 + 节点搜索定位。
 * - 批次下拉：选项来自 GET /seeds/batches（库内去重取值），"加载"请求携带 batch
 * - 节点搜索：输入关键词 → 建议（名称子串匹配）；选中 → 高亮定位（含平移到视口中央）+ 详情面板
 * - 跨视图节点：自动切换结构/实体视图后定位；批次过滤后目标缺席 → 清面板
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, h, nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus, { ElAutocomplete, ElOption } from 'element-plus'

vi.mock('echarts', () => {
  const instance = {
    setOption: vi.fn(),
    on: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    dispatchAction: vi.fn(),
    getWidth: vi.fn(() => 800),
    getHeight: vi.fn(() => 600),
    getModel: vi.fn(() => ({
      getSeriesByIndex: () => ({
        getData: () => ({ getItemLayout: () => [0, 0] }),
        coordinateSystem: { dataToPoint: () => [10, 20] },
      }),
    })),
  }
  return { init: vi.fn(() => instance), __instance: instance }
})

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
}))

import * as echarts from 'echarts'

import { api } from '../src/api/client'
import type { OverviewNode } from '../src/api/types'
import GraphView from '../src/views/seeds/GraphView.vue'
import { nodeSearchSuggestions } from '../src/views/seeds/graphSearch'

const mockedGet = vi.mocked(api.get)
const mockedInstance = (
  echarts as unknown as { __instance: Record<string, ReturnType<typeof vi.fn>> }
).__instance

const LIGHT_VARS: Record<string, string> = {
  '--el-color-success': 'rgb(10, 200, 10)',
  '--el-color-warning': 'rgb(20, 200, 20)',
  '--el-color-primary': 'rgb(30, 200, 30)',
  '--el-color-info': 'rgb(40, 200, 40)',
  '--el-text-color-primary': 'rgb(50, 50, 50)',
  '--el-bg-color-overlay': 'rgb(60, 60, 60)',
  '--el-border-color': 'rgb(70, 70, 70)',
  '--chart-edge-solid': 'rgb(80, 80, 80)',
  '--chart-edge-dashed': 'rgb(90, 90, 90)',
}

function node(over: Partial<OverviewNode> & { id: number; name: string; node_type: string }): OverviewNode {
  return {
    region: null,
    review_status: 'approved',
    counts: { seeds: 1, done: 0, candidates: 0, contacts: 0 },
    ...over,
  }
}

const OVERVIEW = {
  nodes: [
    node({ id: 1, name: '肯尼亚', node_type: 'market', counts: { seeds: 2, done: 1, candidates: 1, contacts: 0 } }),
    node({ id: 2, name: '紧固件', node_type: 'product_line' }),
    node({ id: 3, name: '滨海水务', node_type: 'org', region: '肯尼亚', counts: { seeds: 0, done: 0, candidates: 0, contacts: 1 } }),
  ],
  edges: [
    { source: 2, target: 1, relation_type: 'product_target_market', weight: 1 },
    { source: 3, target: 1, relation_type: 'org_in_market', weight: 1 },
  ],
}

function stubApi() {
  mockedGet.mockImplementation(async (path: string) => {
    if (path === '/seeds/batches') return ['b1', 'b2'] as never
    if (path === '/graph/overview') return OVERVIEW as never
    return {} as never
  })
}

async function mountView() {
  const pinia = createPinia()
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: defineComponent({ render: () => h('div') }) }],
  })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(GraphView, { global: { plugins: [pinia, router, ElementPlus] } })
  await flushPromises()
  return wrapper
}

function batchSelect(wrapper: VueWrapper): VueWrapper {
  return wrapper.findComponent('[data-test="batch-filter"]') as unknown as VueWrapper
}

function nodeSearch(wrapper: VueWrapper): VueWrapper<any> {
  // el-autocomplete 将属性透传到内部 el-input 根 div 上，按组件定位（视图唯一实例）
  return wrapper.findComponent(ElAutocomplete) as unknown as VueWrapper<any>
}

function highlightCalls(): unknown[][] {
  return mockedInstance.dispatchAction.mock.calls.filter(
    ([action]) => (action as { type?: string }).type === 'highlight',
  )
}

async function clickLoad(wrapper: VueWrapper) {
  const button = wrapper.findAll('button').find((item) => item.text() === '加载')
  if (!button) throw new Error('未找到"加载"按钮')
  await button.trigger('click')
  await flushPromises()
}

function lastOverviewParams(): Record<string, unknown> {
  const calls = mockedGet.mock.calls.filter(([path]) => path === '/graph/overview')
  return (calls[calls.length - 1]?.[1] ?? {}) as Record<string, unknown>
}

beforeEach(() => {
  vi.clearAllMocks()
  stubApi()
  document.body.innerHTML = ''
  vi.spyOn(window, 'getComputedStyle').mockReturnValue({
    getPropertyValue: (name: string) => LIGHT_VARS[name] ?? '',
  } as unknown as CSSStyleDeclaration)
})

describe('nodeSearchSuggestions（搜索建议纯函数）', () => {
  const nodes = [
    node({ id: 1, name: '肯尼亚', node_type: 'market' }),
    node({ id: 2, name: '紧固件', node_type: 'product_line' }),
    node({ id: 3, name: 'VMware', node_type: 'org' }),
  ]

  it('空关键词返回全量（聚焦即列出），标签为"名称（类型）"', () => {
    expect(nodeSearchSuggestions(nodes, '')).toEqual([
      { id: 1, label: '肯尼亚（市场/国家）' },
      { id: 2, label: '紧固件（产品线）' },
      { id: 3, label: 'VMware（机构实体）' },
    ])
  })

  it('按名称子串匹配且大小写不敏感；无匹配返回空', () => {
    expect(nodeSearchSuggestions(nodes, '滨海')).toEqual([])
    expect(nodeSearchSuggestions(nodes, '水管')).toEqual([])
    expect(nodeSearchSuggestions(nodes, 'vm')).toEqual([{ id: 3, label: 'VMware（机构实体）' }])
    expect(nodeSearchSuggestions(nodes, 'vM')).toEqual([{ id: 3, label: 'VMware（机构实体）' }])
    expect(nodeSearchSuggestions(nodes, '  紧固  ')).toEqual([{ id: 2, label: '紧固件（产品线）' }])
  })

  it('超过上限截断（列表过长时靠输入收窄）', () => {
    const many = Array.from({ length: 8 }, (_, index) => node({ id: index + 1, name: `节点${index + 1}`, node_type: 'market' }))
    expect(nodeSearchSuggestions(many, '', 5)).toHaveLength(5)
  })
})

describe('GraphView 批次筛选下拉（T198）', () => {
  it('渲染为下拉：选项 = GET /seeds/batches 的库内取值', async () => {
    const wrapper = await mountView()

    expect(mockedGet).toHaveBeenCalledWith('/seeds/batches')
    const values = batchSelect(wrapper)
      .findAllComponents(ElOption)
      .map((option) => option.props('value'))
    expect(values).toEqual(['b1', 'b2'])
  })

  it('选择批次后"加载"：概览请求携带 batch 参数', async () => {
    const wrapper = await mountView()

    batchSelect(wrapper).vm.$emit('update:modelValue', 'b2')
    await nextTick()
    await clickLoad(wrapper)

    expect(lastOverviewParams().batch).toBe('b2')
  })

  it('选项拉取失败不阻断图加载（下拉为空仍可加载）', async () => {
    mockedGet.mockImplementation(async (path: string) => {
      if (path === '/seeds/batches') throw new Error('boom')
      if (path === '/graph/overview') return OVERVIEW as never
      return {} as never
    })
    const wrapper = await mountView()

    expect(batchSelect(wrapper).findAllComponents(ElOption)).toHaveLength(0)
    expect(mockedInstance.setOption).toHaveBeenCalledTimes(1)
  })
})

describe('GraphView 节点搜索定位（T198）', () => {
  it('搜索框渲染为输入式（data-test + 输入建议接线到当前载荷）', async () => {
    const wrapper = await mountView()
    const auto = nodeSearch(wrapper)
    expect(auto.exists()).toBe(true)
    expect(wrapper.find('[data-test="node-search"]').exists()).toBe(true)
    expect((auto.props('placeholder') as string)).toContain('搜索节点')

    const fetch = auto.props('fetchSuggestions') as (
      query: string,
      callback: (items: Array<{ id: number; label: string }>) => void,
    ) => void
    let items: Array<{ id: number; label: string }> = []
    fetch('滨海', (result) => {
      items = result
    })
    expect(items).toEqual([{ id: 3, label: '滨海水务（机构实体）' }])
  })

  it('输入关键词出现匹配建议（DOM 建议列表）', async () => {
    const wrapper = await mountView()

    await wrapper.find('input[placeholder="搜索节点并定位"]').setValue('滨海')
    await flushPromises()

    expect(document.body.textContent).toContain('滨海水务（机构实体）')
  })

  it('选中结构视图节点：高亮定位 + 平移到视口中央 + 打开详情面板', async () => {
    const wrapper = await mountView()

    nodeSearch(wrapper).vm.$emit('select', { id: 2, label: '紧固件（产品线）' })
    await flushPromises()

    // 结构视图渲染序 [肯尼亚(1), 紧固件(2)] → dataIndex 1
    expect(mockedInstance.dispatchAction).toHaveBeenCalledWith({
      type: 'highlight',
      seriesIndex: 0,
      dataIndex: 1,
    })
    expect(mockedInstance.dispatchAction).toHaveBeenCalledWith({
      type: 'showTip',
      seriesIndex: 0,
      dataIndex: 1,
    })
    // 节点像素位 (10,20)（mock）→ 800×600 容器居中：dx=390, dy=280
    expect(mockedInstance.dispatchAction).toHaveBeenCalledWith({
      type: 'graphRoam',
      seriesIndex: 0,
      dx: 390,
      dy: 280,
    })
    const panel = wrapper.find('.node-panel')
    expect(panel.exists()).toBe(true)
    expect(panel.text()).toContain('紧固件')
    expect(panel.text()).toContain('种子 1 条')
  })

  it('选中另一视图节点：自动切换实体视图、重渲并定位', async () => {
    const wrapper = await mountView()
    expect(mockedInstance.setOption).toHaveBeenCalledTimes(1)

    nodeSearch(wrapper).vm.$emit('select', { id: 3, label: '滨海水务（机构实体）' })
    await flushPromises()

    expect(mockedInstance.setOption).toHaveBeenCalledTimes(2)
    expect(wrapper.find('.el-radio-button.is-active').text()).toBe('实体视图')
    // 实体视图渲染序 [肯尼亚(1), 滨海水务(3)] → dataIndex 1
    expect(mockedInstance.dispatchAction).toHaveBeenCalledWith({
      type: 'highlight',
      seriesIndex: 0,
      dataIndex: 1,
    })
  })

  it('清空搜索：关闭详情面板且不再派发新的定位高亮', async () => {
    const wrapper = await mountView()
    nodeSearch(wrapper).vm.$emit('select', { id: 1, label: '肯尼亚（市场/国家）' })
    await flushPromises()
    const highlightsAfterSelect = highlightCalls().length

    nodeSearch(wrapper).vm.$emit('clear')
    await flushPromises()

    expect(wrapper.find('.node-panel').exists()).toBe(false)
    expect(highlightCalls()).toHaveLength(highlightsAfterSelect)
  })

  it('批次过滤后目标不在图内：面板与搜索词被清理（不展示陈旧节点）', async () => {
    let overviewCall = 0
    mockedGet.mockImplementation(async (path: string) => {
      if (path === '/seeds/batches') return ['b1', 'b2'] as never
      if (path === '/graph/overview') {
        overviewCall += 1
        if (overviewCall === 1) return OVERVIEW as never
        return { nodes: [OVERVIEW.nodes[1]], edges: [] } as never
      }
      return {} as never
    })
    const wrapper = await mountView()

    nodeSearch(wrapper).vm.$emit('select', { id: 3, label: '滨海水务（机构实体）' })
    await flushPromises()
    expect(wrapper.find('.node-panel').exists()).toBe(true)

    batchSelect(wrapper).vm.$emit('update:modelValue', 'b1')
    await nextTick()
    await clickLoad(wrapper)

    expect(wrapper.find('.node-panel').exists()).toBe(false)
    expect(nodeSearch(wrapper).props('modelValue')).toBe('')
  })
})
