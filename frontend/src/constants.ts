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
