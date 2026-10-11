/**
 * T157 组件测试（002-frontend-theme，红阶段）：MainLayout 页头主题切换控件。
 * 对应 FR-001/002：全局一步可达、当前模式可辨识、用户操作驱动 store.toggle 持久化。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus, { ElSwitch } from 'element-plus'

import { api } from '../src/api/client'
import MainLayout from '../src/layouts/MainLayout.vue'
import { useThemeStore } from '../src/stores/theme'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
}))

const mockedApi = vi.mocked(api)

async function mountWithPinia() {
  const pinia = createPinia()
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/',
        component: defineComponent({ render: () => h('div') }),
        meta: { title: '总览' },
      },
    ],
  })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(MainLayout, {
    global: { plugins: [pinia, router, ElementPlus] },
  })
  await flushPromises()
  return { wrapper, theme: useThemeStore(pinia) }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.get.mockResolvedValue({})
  mockedApi.put.mockResolvedValue({})
  document.documentElement.classList.remove('dark')
})

describe('MainLayout 页头主题切换控件', () => {
  it('页头渲染切换控件且当前态可辨识（默认 light）', async () => {
    const { wrapper } = await mountWithPinia()
    const control = wrapper.find('[data-test="theme-switch"]')
    expect(control.exists()).toBe(true)
    expect(wrapper.findComponent(ElSwitch).props('modelValue')).toBe(false)
    expect(wrapper.find('.el-switch__input').attributes('aria-label')).toContain('浅色')
  })

  it('用户切换：同帧翻转全局类、控件态更新、PUT 持久化', async () => {
    const { wrapper, theme } = await mountWithPinia()

    // 经由公开 v-model 交互（等价用户点按开关）
    wrapper.findComponent(ElSwitch).vm.$emit('update:modelValue', true)
    await flushPromises()

    expect(theme.current).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(wrapper.findComponent(ElSwitch).props('modelValue')).toBe(true)
    expect(mockedApi.put).toHaveBeenCalledWith('/settings', { values: { ui_theme: 'dark' } })
  })

  it('dark 首帧（服务端注入）下控件初始即选中并标注深色', async () => {
    document.documentElement.classList.add('dark')
    const { wrapper } = await mountWithPinia()
    expect(wrapper.find('[data-test="theme-switch"]').exists()).toBe(true)
    expect(wrapper.findComponent(ElSwitch).props('modelValue')).toBe(true)
    expect(wrapper.find('.el-switch__input').attributes('aria-label')).toContain('深色')
  })
})
