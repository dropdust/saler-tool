/**
 * T161 单元测试（002-frontend-theme，红阶段）：启动同步 syncFromServer —— 校正与竞态守卫。
 * 契约：contracts/theme-contract.md §3 / research.md R4（dev 兜底与异常校正）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { api } from '../src/api/client'
import { useThemeStore } from '../src/stores/theme'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}))

const mockedGet = vi.mocked(api.get)
const mockedPut = vi.mocked(api.put)

beforeEach(() => {
  vi.clearAllMocks()
  mockedPut.mockResolvedValue({} as never)
  document.documentElement.classList.remove('dark')
  setActivePinia(createPinia())
})

describe('themeStore.syncFromServer', () => {
  it('服务器 dark 且 DOM 为 light（无注入场景）：校正为 dark 并加类', async () => {
    mockedGet.mockResolvedValue({ ui_theme: 'dark' } as never)
    const store = useThemeStore()

    await store.syncFromServer()

    expect(store.current).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('服务器值非法：归一为 light（与后端同规则）', async () => {
    mockedGet.mockResolvedValue({ ui_theme: 'blue' } as never)
    document.documentElement.classList.add('dark')
    const store = useThemeStore()

    await store.syncFromServer()

    expect(store.current).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('userTouched 守卫：用户已手动切换后，启动同步不得覆盖', async () => {
    mockedGet.mockResolvedValue({ ui_theme: 'light' } as never) // 服务器仍是旧值
    const store = useThemeStore()

    await store.toggle() // 用户切到 dark（PUT 未落或慢）
    expect(store.current).toBe('dark')

    await store.syncFromServer() // 迟到的启动同步

    expect(store.current).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('GET 失败：静默保持现状，不抛错不改类', async () => {
    mockedGet.mockRejectedValue(new Error('network down'))
    const store = useThemeStore()

    await expect(store.syncFromServer()).resolves.toBeUndefined()

    expect(store.current).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })
})
