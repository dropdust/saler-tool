/** 本地 API 数据类型（对齐 contracts/local-api.md 与 api/serializers.py）。 */

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface JobPayload {
  id: number
  job_type: string
  name: string | null
  status: 'queued' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled'
  progress: Record<string, unknown>
  result: Record<string, unknown> | null
  error: string | null
  ref_type: string | null
  ref_id: number | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
}

export interface GraphNode {
  id: number
  node_type: 'product_line' | 'persona' | 'market' | 'org'
  name: string
  parent_id: number | null
  region: string | null
  attributes: Record<string, unknown>
  confidence: number | null
  source: string
  evidence_url: string | null
  review_status: 'pending' | 'approved' | 'rejected'
  status: 'active' | 'disabled'
}

export interface NodeTerm {
  id: number
  node_id: number
  lang: string
  term: string
  term_type: 'name' | 'alias' | 'synonym' | 'term'
  source: string
  review_status: string
}

export interface GraphEdge {
  id: number
  from_node_id: number
  to_node_id: number
  relation_type: string
  source: string
  review_status: string
}

export interface Seed {
  id: number
  query: string
  lang: string
  product_line_id: number | null
  persona_id: number | null
  market_id: number | null
  priority: number
  batch: string | null
  source_node_id: number | null
  template: string | null
  status: 'pending' | 'running' | 'done' | 'invalid'
  source: 'manual' | 'llm' | 'search' | 'import'
  confidence: number | null
  review_status: 'pending' | 'approved' | 'rejected'
  n_candidates: number
  n_contacts: number
  note: string | null
  last_run_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface StatsRow {
  key: number | string | null
  name: string
  seeds: number
  done: number
  candidates: number
  contacts: number
}

export interface OverviewNode {
  id: number
  node_type: string
  name: string
  region: string | null
  review_status: string
  counts: { seeds: number; done: number; candidates: number; contacts: number }
}

export interface OverviewEdge {
  source: number
  target: number
  relation_type: string
  weight: number
}

export interface OverviewPayload {
  nodes: OverviewNode[]
  edges: OverviewEdge[]
}
