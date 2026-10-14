/** 领域常量与标签（UI 统一口径）。 */

export const LANGS: Array<{ code: string; label: string }> = [
  { code: 'en', label: '英语' },
  { code: 'zh', label: '中文' },
  { code: 'ru', label: '俄语' },
  { code: 'ar', label: '阿拉伯语' },
  { code: 'es', label: '西班牙语' },
  { code: 'pt', label: '葡萄牙语' },
  { code: 'fr', label: '法语' },
  { code: 'de', label: '德语' },
  { code: 'it', label: '意大利语' },
  { code: 'pl', label: '波兰语' },
  { code: 'tr', label: '土耳其语' },
  { code: 'vi', label: '越南语' },
  { code: 'th', label: '泰语' },
  { code: 'id', label: '印尼语' },
  { code: 'hi', label: '印地语' },
  { code: 'fa', label: '波斯语' },
  { code: 'uk', label: '乌克兰语' },
]

export function langLabel(code: string | null | undefined): string {
  if (!code) return '—'
  return LANGS.find((item) => item.code === code)?.label ?? code
}

/**
 * 语言筛选选项（003）：统一语言表全量（固定顺序、"中文标签（code）"）＋ 库内非标准精确取值
 * （原样 code、按传入顺序追加、去重）。存库原值即选项值——`EN` 与 `en` 为两个独立选项（精确匹配语义）。
 */
export function langFilterOptions(present: string[]): Array<{ value: string; label: string }> {
  const known = LANGS.map((item) => ({ value: item.code, label: `${item.label}（${item.code}）` }))
  const seen = new Set(known.map((item) => item.value))
  const extras: Array<{ value: string; label: string }> = []
  for (const code of present) {
    if (seen.has(code)) continue
    seen.add(code)
    extras.push({ value: code, label: code })
  }
  return [...known, ...extras]
}

export const NODE_TYPE_LABELS: Record<string, string> = {
  product_line: '产品线',
  persona: '客户角色',
  market: '市场/国家',
  org: '机构实体',
}

export const RELATION_LABELS: Record<string, string> = {
  product_fit_persona: '产品线×客户角色（适配）',
  product_target_market: '产品重点市场',
  org_in_market: '机构归属市场',
  org_has_persona: '机构属于客户角色',
}

export const PRIORITY_LABELS: Record<number, string> = { 1: '高', 2: '中', 3: '低' }

export const SOURCE_LABELS: Record<string, string> = {
  manual: '手工',
  llm: '大模型',
  search: '检索',
  import: '导入',
  harvest: '回灌',
  crawl: '爬取',
}

/**
 * 任务类型 → 跳转路由（005 契约 §5）：任务中心/通知点击的落点。
 * 未映射类型返回 null——调用方回退为"打开任务抽屉定位该任务"（不猜测落点）。
 */
export const JOB_TYPE_ROUTES: Record<string, string> = {
  crawl: '/leads/jobs',
  campaign_send: '/campaigns',
  seed_discover: '/seeds/review',
  ai_seed_expand: '/seeds/review',
  ai_seed_translate: '/seeds/review',
  ai_term_translate: '/seeds/graph-manage',
  ingest_harvest: '/seeds/review',
  seed_validate: '/seeds',
  ai_content_draft: '/content',
  ai_content_translate: '/content',
  company_import: '/leads',
  backup: '/settings/backup',
  restore: '/settings/backup',
  export_all: '/settings/backup',
  data_dir_move: '/settings',
}

export function jobRoute(jobType: string): string | null {
  return JOB_TYPE_ROUTES[jobType] ?? null
}
