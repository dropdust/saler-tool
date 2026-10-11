/**
 * 主题 store（002-frontend-theme）：唯一的 DOM 类操作者（视图禁止直接操作）。
 * - current：运行时主题事实，初值 = 服务端在 GET / 注入的 html.dark 类（首帧值）；
 * - toggle()：同帧翻转 DOM 类（即时生效）→ PUT /settings 持久化；失败保留会话态、不回滚；
 * - normalizeTheme：与后端同规则，仅 "dark" 为暗色，其余一律回退 "light"（FR-006）。
 *
 * 契约：contracts/theme-contract.md §3；状态机：data-model.md。
 */

import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'

import { ApiError, api } from '../api/client'

export type ThemeMode = 'light' | 'dark'

const DARK = 'dark'

/** 归一（与后端 settings_service 同规则）。 */
export function normalizeTheme(value: unknown): ThemeMode {
  return value === DARK ? 'dark' : 'light'
}

/** 从 DOM 读运行时主题（生产环境 = 后端注入的首帧值）。 */
export function currentThemeFromDom(): ThemeMode {
  if (typeof document === 'undefined') return 'light'
  return document.documentElement.classList.contains(DARK) ? 'dark' : 'light'
}

/** 应用主题到 DOM（唯一出口）。 */
export function applyTheme(theme: ThemeMode): void {
  document.documentElement.classList.toggle(DARK, theme === DARK)
}

export const useThemeStore = defineStore('theme', {
  state: () => ({
    current: currentThemeFromDom() as ThemeMode,
    /** 用户是否已手动操作（启动同步守卫：不覆盖用户刚做的切换，R4）。 */
    userTouched: false,
  }),
  actions: {
    async toggle(): Promise<void> {
      this.userTouched = true
      this.current = this.current === DARK ? 'light' : 'dark'
      applyTheme(this.current)
      try {
        await api.put('/settings', { values: { ui_theme: this.current } })
      } catch (error) {
        if (!(error instanceof ApiError)) {
          // ApiError 场景 api/client 已统一提示；此处覆盖网络级失败
          ElMessage.error('主题偏好未保存（下次启动将回到上次保存的主题）')
        }
        // 保留会话内已应用主题，不回滚（FR-003 即时性优先）
      }
    },
    /**
     * 启动校正：dev 无注入 / 注入降级 / 极端恢复场景下与设置对齐。
     * userTouched 守卫：不覆盖用户刚做的切换（R4 竞态防护）；失败静默保持现状。
     */
    async syncFromServer(): Promise<void> {
      try {
        const settings = await api.get<Record<string, unknown>>('/settings')
        const server = normalizeTheme(settings?.ui_theme)
        if (!this.userTouched && server !== this.current) {
          this.current = server
          applyTheme(server)
        }
      } catch {
        // 静默保持现状，不阻断使用
      }
    },
  },
})
