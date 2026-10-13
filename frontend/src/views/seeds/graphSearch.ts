/**
 * 图谱节点搜索（T198）：建议项组装纯函数。
 * 输入关键词 → 名称子串匹配（大小写不敏感）→ 定位用建议项（id + 带类型的展示标签）。
 * 空关键词返回全量（聚焦即列出，等价旧"下拉选择"）；超过上限截断（列表过长时靠输入收窄）。
 */

import type { OverviewNode } from '../../api/types'
import { NODE_TYPE_LABELS } from '../../constants'

export interface NodeSuggestion {
  id: number
  label: string
}

export function nodeSearchSuggestions(
  nodes: OverviewNode[],
  query: string,
  limit = 50,
): NodeSuggestion[] {
  const keyword = query.trim().toLowerCase()
  return nodes
    .filter((node) => !keyword || node.name.toLowerCase().includes(keyword))
    .slice(0, limit)
    .map((node) => ({
      id: node.id,
      label: `${node.name}（${NODE_TYPE_LABELS[node.node_type] ?? node.node_type}）`,
    }))
}
