/**
 * T155 单元测试（002-frontend-theme）：主题 store —— 翻转/PUT 调用与失败保留/归一/DOM 初值。
 * 对应 FR-001~004 与 data-model.md 状态机；契约见 contracts/theme-contract.md §3。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { api } from '../src/api/client'
import { normalizeTheme, useThemeStore } from '../src/stores/theme'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}))

const mockedPut = vi.mocked(api.put)

beforeEach(() => {
  vi.clearAllMocks()
  document.documentElement.classList.remove('dark')
  setActivePinia(createPinia())
})

describe('normalizeTheme 归一', () => {
  it('"dark" 保持，其余一律归 "light"', () => {
    expect(normalizeTheme('dark')).toBe('dark')
    expect(normalizeTheme('light')).toBe('light')
    expect(normalizeTheme('blue')).toBe('light')
    expect(normalizeTheme('DARK')).toBe('light')
    expect(normalizeTheme(undefined)).toBe('light')
    expect(normalizeTheme(123)).toBe('light')
  })
})

describe('useThemeStore', () => {
  it('current 初值从 DOM 读取（服务端注入值即首帧事实）', () => {
    document.documentElement.classList.add('dark')
    const store = useThemeStore()
    expect(store.current).toBe('dark')
  })

  it('toggle：同帧翻转 DOM 类并以 ui_theme 调用 PUT /settings', async () => {
    mockedPut.mockResolvedValue({} as never)
    const store = useThemeStore()
    expect(document.documentElement.classList.contains('dark')).toBe(false)

    await store.toggle()

    expect(store.current).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(mockedPut).toHaveBeenCalledTimes(1)
    expect(mockedPut).toHaveBeenCalledWith('/settings', { values: { ui_theme: 'dark' } })

    await store.toggle()
    expect(store.current).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(mockedPut).toHaveBeenLastCalledWith('/settings', { values: { ui_theme: 'light' } })
  })

  it('PUT 失败：保留会话内已应用主题（不回滚）且不抛错', async () => {
    mockedPut.mockRejectedValue(new Error('network down'))
    const store = useThemeStore()

    await expect(store.toggle()).resolves.toBeUndefined()

    expect(store.current).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })
})
