/**
 * T166 单元测试（002-frontend-theme，红阶段）：图表调色板纯函数。
 * - readThemePalette()：经 computed CSS 变量取色；变量缺失时兜底；
 * - nodeColor()：节点状态色语义与既有 GraphView.colorOf 一致（R5）。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { nodeColor, readThemePalette } from '../src/theme/palette'

let varMap: Record<string, string> = {}

beforeEach(() => {
  varMap = {}
  vi.spyOn(window, 'getComputedStyle').mockReturnValue({
    getPropertyValue: (name: string) => varMap[name] ?? '',
  } as unknown as CSSStyleDeclaration)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('readThemePalette', () => {
  it('从 computed CSS 变量读取两种主题下的取色', () => {
    varMap = {
      '--el-color-success': 'rgb(1, 200, 1)',
      '--el-color-warning': 'rgb(2, 200, 2)',
      '--el-color-primary': 'rgb(3, 200, 3)',
      '--el-color-info': 'rgb(4, 200, 4)',
      '--el-text-color-primary': 'rgb(5, 5, 5)',
      '--el-bg-color-overlay': 'rgb(6, 6, 6)',
      '--el-border-color': 'rgb(7, 7, 7)',
      '--chart-edge-solid': 'rgb(8, 8, 8)',
      '--chart-edge-dashed': 'rgb(9, 9, 9)',
    }
    const palette = readThemePalette()
    expect(palette.success).toBe('rgb(1, 200, 1)')
    expect(palette.warning).toBe('rgb(2, 200, 2)')
    expect(palette.primary).toBe('rgb(3, 200, 3)')
    expect(palette.info).toBe('rgb(4, 200, 4)')
    expect(palette.textPrimary).toBe('rgb(5, 5, 5)')
    expect(palette.tooltipBg).toBe('rgb(6, 6, 6)')
    expect(palette.tooltipBorder).toBe('rgb(7, 7, 7)')
    expect(palette.edgeSolid).toBe('rgb(8, 8, 8)')
    expect(palette.edgeDashed).toBe('rgb(9, 9, 9)')
  })

  it('变量缺失时回退既有亮色口径（不抛错、不空值）', () => {
    const palette = readThemePalette()
    expect(palette.success).toBe('#67c23a')
    expect(palette.warning).toBe('#e6a23c')
    expect(palette.primary).toBe('#409eff')
    expect(palette.info).toBe('#c0c4cc')
    expect(palette.edgeSolid).toBe('#b1b3b8')
    expect(palette.edgeDashed).toBe('#7a7d85')
    for (const value of Object.values(palette)) {
      expect(String(value).length).toBeGreaterThan(0)
    }
  })
})

describe('nodeColor 状态语义（与 GraphView 既有口径一致）', () => {
  const palette = readThemePalette()
  it('contacts>0 → success 优先', () => {
    expect(nodeColor({ seeds: 9, done: 9, candidates: 9, contacts: 1 }, palette)).toBe(palette.success)
  })
  it('done>0（无 contacts）→ warning', () => {
    expect(nodeColor({ seeds: 9, done: 1, candidates: 3, contacts: 0 }, palette)).toBe(palette.warning)
  })
  it('seeds>0（含 candidates）→ primary', () => {
    expect(nodeColor({ seeds: 1, done: 0, candidates: 5, contacts: 0 }, palette)).toBe(palette.primary)
  })
  it('全 0 → info', () => {
    expect(nodeColor({ seeds: 0, done: 0, candidates: 0, contacts: 0 }, palette)).toBe(palette.info)
  })
})
