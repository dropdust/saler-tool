/**
 * T167 单元测试（002-frontend-theme，红阶段）：GraphView ECharts 主题化。
 * mock echarts（不触真实 canvas）：初始渲染取色来自 palette；主题切换触发整体重渲并取到新主题色。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, h, nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'

vi.mock('echarts', () => {
  const instance = {
    setOption: vi.fn(),
    on: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
  }
  return { init: vi.fn(() => instance), __instance: instance }
})

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
}))

import * as echarts from 'echarts'

import { api } from '../src/api/client'
import GraphView from '../src/views/seeds/GraphView.vue'
import { applyTheme, useThemeStore } from '../src/stores/theme'

const mockedGet = vi.mocked(api.get)
const mockedPut = vi.mocked(api.put)
const mockedInstance = (echarts as unknown as { __instance: Record<string, ReturnType<typeof vi.fn>> })
  .__instance

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

const DARK_VARS: Record<string, string> = {
  ...LIGHT_VARS,
  '--el-text-color-primary': 'rgb(210, 210, 210)',
  '--el-bg-color-overlay': 'rgb(30, 30, 30)',
  '--chart-edge-solid': 'rgb(100, 100, 100)',
  '--chart-edge-dashed': 'rgb(110, 110, 110)',
}

let varMap: Record<string, string> = {}

async function mountGraphView() {
  const pinia = createPinia()
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: defineComponent({ render: () => h('div') }) }],
  })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(GraphView, { global: { plugins: [pinia, router, ElementPlus] } })
  await flushPromises()
  return { wrapper, theme: useThemeStore(pinia) }
}

beforeEach(() => {
  vi.clearAllMocks()
  varMap = { ...LIGHT_VARS }
  vi.spyOn(window, 'getComputedStyle').mockReturnValue({
    getPropertyValue: (name: string) => varMap[name] ?? '',
  } as unknown as CSSStyleDeclaration)
  document.documentElement.classList.remove('dark')
  mockedPut.mockResolvedValue({} as never)
  mockedGet.mockResolvedValue({
    nodes: [
      {
        id: 1,
        name: '肯尼亚',
        node_type: 'market',
        region: null,
        counts: { seeds: 2, done: 0, candidates: 1, contacts: 0 },
      },
    ],
    edges: [],
  } as never)
})

describe('GraphView 主题化', () => {
  it('初始渲染：label/节点色/工具提示色取自 palette（亮色）', async () => {
    await mountGraphView()

    expect(echarts.init).toHaveBeenCalledTimes(1)
    expect(mockedInstance.setOption).toHaveBeenCalledTimes(1)
    const option = mockedInstance.setOption.mock.calls[0][0] as {
      tooltip: { backgroundColor: string }
      series: { label: { color: string }; data: { itemStyle: { color: string } }[] }[]
    }
    expect(option.series[0].label.color).toBe(LIGHT_VARS['--el-text-color-primary'])
    expect(option.series[0].data[0].itemStyle.color).toBe(LIGHT_VARS['--el-color-primary']) // seeds>0
    expect(option.tooltip.backgroundColor).toBe(LIGHT_VARS['--el-bg-color-overlay'])
  })

  it('主题切换：触发整体重渲且取到暗色新值；图例圆点改用 CSS 变量类', async () => {
    const { wrapper, theme } = await mountGraphView()
    expect(mockedInstance.setOption).toHaveBeenCalledTimes(1)

    // 模拟切到 dark（html 类 + store 状态；取色表同步为暗色）
    varMap = { ...DARK_VARS }
    applyTheme('dark')
    theme.current = 'dark'
    await nextTick()
    await flushPromises()

    expect(mockedInstance.setOption).toHaveBeenCalledTimes(2)
    const option = mockedInstance.setOption.mock.calls[1][0] as {
      series: { label: { color: string } }[]
    }
    expect(option.series[0].label.color).toBe(DARK_VARS['--el-text-color-primary'])

    // 图例圆点：使用语义类（背景由 --el-* 变量承载），不再内联硬编码色
    expect(wrapper.find('.dot-success').exists()).toBe(true)
    expect(wrapper.find('.dot-warning').exists()).toBe(true)
    expect(wrapper.find('.dot-primary').exists()).toBe(true)
    expect(wrapper.find('.dot-info').exists()).toBe(true)
    expect(wrapper.html()).not.toContain('#67c23a')
  })
})
