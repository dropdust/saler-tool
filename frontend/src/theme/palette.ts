/**
 * 图表主题调色板（002-frontend-theme，纯函数层）。
 * ECharts 为 canvas 渲染、不消费 CSS 变量——在每次重渲时经 computed CSS 变量取色（R5）。
 * 契约：contracts/theme-contract.md §3（图表颜色经 palette 读取；禁止硬编码）。
 */

export interface ThemePalette {
  success: string
  warning: string
  primary: string
  info: string
  textPrimary: string
  tooltipBg: string
  tooltipText: string
  tooltipBorder: string
  edgeSolid: string
  edgeDashed: string
}

/** 亮色口径兜底（变量缺失时使用，如非浏览器环境）。 */
const FALLBACK: ThemePalette = {
  success: '#67c23a',
  warning: '#e6a23c',
  primary: '#409eff',
  info: '#c0c4cc',
  textPrimary: '#303133',
  tooltipBg: '#ffffff',
  tooltipText: '#303133',
  tooltipBorder: '#e4e7ed',
  edgeSolid: '#b1b3b8',
  edgeDashed: '#7a7d85',
}

/** 读取当前主题下的图表调色板（含 html.dark 切换后的新值）。 */
export function readThemePalette(): ThemePalette {
  const style = getComputedStyle(document.documentElement)
  const read = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback
  return {
    success: read('--el-color-success', FALLBACK.success),
    warning: read('--el-color-warning', FALLBACK.warning),
    primary: read('--el-color-primary', FALLBACK.primary),
    info: read('--el-color-info', FALLBACK.info),
    textPrimary: read('--el-text-color-primary', FALLBACK.textPrimary),
    tooltipBg: read('--el-bg-color-overlay', FALLBACK.tooltipBg),
    tooltipText: read('--el-text-color-primary', FALLBACK.tooltipText),
    tooltipBorder: read('--el-border-color', FALLBACK.tooltipBorder),
    edgeSolid: read('--chart-edge-solid', FALLBACK.edgeSolid),
    edgeDashed: read('--chart-edge-dashed', FALLBACK.edgeDashed),
  }
}

export interface NodeCounts {
  seeds: number
  done: number
  candidates: number
  contacts: number
}

/** 节点状态色语义（与既有 GraphView 口径一致）：contacts>0 → success、done>0 → warning、seeds>0 → primary、否则 info。 */
export function nodeColor(counts: NodeCounts, palette: ThemePalette): string {
  if (counts.contacts > 0) return palette.success
  if (counts.done > 0) return palette.warning
  if (counts.seeds > 0) return palette.primary
  return palette.info
}
