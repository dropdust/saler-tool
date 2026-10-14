/**
 * 候选域名检索溯源（异常域名排查）：详情弹窗的行组装与摘要（纯函数，供组件与测试共用）。
 * 来源链路：挖掘任务 → 种子（query 词）→ domain_seed_hit → 候选域名。
 */

import type { DomainSeedHit } from '../../api/types'

export interface ProvenanceRow {
  query: string
  jobLabel: string
  timeLabel: string
}

export function provenanceSummary(hits: DomainSeedHit[]): string {
  if (!hits.length) {
    return '无检索命中记录（如客户导入来源，或尚未经过检索发现）'
  }
  return `共 ${hits.length} 条检索词命中（同一域名可被多条 query 命中，逐条给出）`
}

export function provenanceRows(hits: DomainSeedHit[]): ProvenanceRow[] {
  return hits.map((hit) => ({
    query: hit.query,
    jobLabel: hit.job_id == null ? '—' : `任务 #${hit.job_id}`,
    timeLabel: (hit.first_seen_at || '').slice(0, 19).replace('T', ' ') || '—',
  }))
}
