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
  status: 'queued' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled' | 'interrupted'
  progress: Record<string, unknown>
  result: Record<string, unknown> | null
  error: string | null
  ref_type: string | null
  ref_id: number | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  /** 任务能力（目录派生，005 契约 §4）：前端据此渲染暂停/重跑按钮 */
  can_pause: boolean
  rerunnable: boolean
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

export interface DomainRow {
  id: number
  domain: string
  homepage_url: string | null
  title: string | null
  snippet: string | null
  source: string | null
  status: 'pending' | 'fetching' | 'done' | 'no_contact' | 'failed'
  attempts: number
  last_error: string | null
  fetched_pages: number
  country: string | null
  country_source: string | null
  language: string | null
  language_source: string | null
  is_excluded: boolean
  exclusion_reason: string | null
  company_id: number | null
  seed_hits_count: number | null
  last_crawled_at: string | null
  created_at: string | null
}

export interface DomainSeedHit {
  seed_id: number
  query: string
  lang: string | null
  source: string | null
  job_id: number | null
  first_seen_at: string | null
}

export interface DomainDetail extends DomainRow {
  seed_hits: DomainSeedHit[]
}

export interface CompanyRow {
  id: number
  name: string | null
  country: string | null
  language: string | null
  status: 'new' | 'contacted' | 'replied' | 'won' | 'lost' | 'invalid'
  is_excluded: boolean
  exclusion_reason: string | null
  tags: string[]
  source: string
  note: string | null
  domain: string | null
  contacts_count: number
  created_at: string | null
  updated_at: string | null
  contacts?: ContactRow[]
}

export interface ContactRow {
  id: number
  company_id: number
  domain_id: number | null
  type: string
  value: string
  value_normalized: string
  category: string
  source_url: string | null
  validity: string
  is_primary: boolean
  created_at: string | null
}

export interface CrawlJobRow {
  id: number
  name: string | null
  scope: { seed_ids?: number[] | null }
  config: Record<string, unknown>
  status: string
  stats: Record<string, number>
  started_at: string | null
  finished_at: string | null
  created_at: string | null
}

export interface SearchProviderRow {
  id: number
  type_key: string
  name: string
  endpoint: string | null
  priority: number
  enabled: boolean
  params: Record<string, unknown>
  used_today: number
  health: 'unknown' | 'healthy' | 'failing'
  last_test_at: string | null
  last_test_result: string | null
  last_error_kind: string | null
  last_error_at: string | null
}

export interface ExclusionRuleRow {
  id: number
  rule_type: 'keyword' | 'domain' | 'list'
  pattern: string
  enabled: boolean
  note: string | null
  created_at: string | null
}

export interface ContentVersionRow {
  id: number
  variant_id: number
  version_no: number
  subject: string | null
  body_md: string
  variables: string[]
  change_note: string | null
  created_by: string
  created_at: string | null
}

export interface ContentVariantRow {
  id: number
  theme_id: number
  lang: string
  status: 'draft' | 'review' | 'published' | 'archived'
  source: 'manual' | 'llm_assisted' | 'llm_translated'
  parent_variant_id: number | null
  current: ContentVersionRow | null
  created_at: string | null
  updated_at: string | null
}

export interface ContentThemeRow {
  id: number
  name: string
  content_type: 'email' | 'sms' | 'social_message'
  master_lang: string
  description: string | null
  variants_count: number
  variants?: ContentVariantRow[]
  created_at: string | null
  updated_at: string | null
}

export interface PublishedVariantRow {
  id: number
  theme_id: number
  theme_name: string
  lang: string
  subject: string | null
}

export interface ChannelRow {
  id: number
  name: string
  channel_type: 'email' | 'sms'
  config: Record<string, unknown>
  identity: Record<string, string | null>
  daily_limit: number
  rate_per_minute: number
  concurrency: number
  status: 'active' | 'disabled'
  health: 'unknown' | 'healthy' | 'failing'
  last_check_at: string | null
  last_check_result: string | null
  used_today: number
  used_today_date: string | null
  total_sent: number
  secret_set: boolean
  created_at: string | null
  updated_at: string | null
}

export interface ChannelUsageRow {
  used_today: number
  daily_limit: number
  rate_per_minute: number
  concurrency: number
  remaining_today: number | null
  total_sent: number
  health: string
  status: string
  last_check_at: string | null
  last_check_result: string | null
}

export interface SchemaProperty {
  type?: string
  title?: string
  format?: string
  enum?: string[]
  default?: unknown
  description?: string
  examples?: string[]
}

export interface ChannelManifest {
  kind: 'mail' | 'sms'
  type_key: string
  display_name: string
  config_schema: {
    properties?: Record<string, SchemaProperty>
    required?: string[]
  }
  secret_fields: string[]
  presets: Record<string, Record<string, unknown>>
}

export interface CampaignRoundRow {
  id: number
  campaign_id: number
  round_no: number
  content_theme_id: number | null
  interval_days: number | null
  condition: string
  status: 'pending' | 'running' | 'done' | 'cancelled'
  stats: Record<string, number>
  started_at: string | null
  finished_at: string | null
}

export interface CampaignRow {
  id: number
  name: string
  status: 'draft' | 'running' | 'paused' | 'completed' | 'cancelled'
  content_theme_id: number | null
  audience: Record<string, unknown>
  lang_strategy: 'auto' | 'fixed'
  fixed_lang: string | null
  fallback_lang: string | null
  schedule: Record<string, unknown>
  estimate: Record<string, unknown>
  stats: Record<string, number>
  started_at: string | null
  finished_at: string | null
  created_at: string | null
  updated_at: string | null
  rounds?: CampaignRoundRow[]
  channels?: Array<{ channel_id: number; role: string; name: string | null }>
  active_job_id?: number | null
}

export interface SendRecordRow {
  id: number
  campaign_id: number
  round_no: number
  company_id: number
  company_name: string | null
  contact_id: number
  contact_value: string
  channel_id: number | null
  channel_name: string | null
  content_variant_id: number | null
  content_version_id: number | null
  lang_used: string | null
  fallback_used: boolean
  status: 'pending' | 'sent' | 'failed' | 'bounced' | 'skipped' | 'suppressed'
  skip_reason: string | null
  error_code: string | null
  error_message: string | null
  scheduled_at: string | null
  sent_at: string | null
  created_at: string | null
}

export interface EstimateRow {
  audience_count: number
  message_count: number
  by_lang: Record<string, number>
  by_channel: Record<string, number>
  fallback_count: number
  suppressed: number
  skipped: number
  eta_minutes: number
  daily_capacity: number | null
}

export interface CampaignReportRow {
  campaign: { id: number; name: string; status: string; started_at: string | null; finished_at: string | null }
  totals: Record<string, number>
  by_channel: Record<string, Record<string, number>>
  by_lang: Record<string, Record<string, number>>
  by_round: Record<string, Record<string, number>>
}

export interface LlmCallMessage {
  role: string
  content: unknown
}

/** LLM 调用明细行（llm_call 表 / `llm_call_to_dict`）：逐次尝试的完整输入与原始输出。 */
export interface LlmCallRow {
  id: number
  ts: string | null
  job_id: number | null
  call_index: number
  phase: string | null
  operation: string
  provider: string
  model: string
  attempt: number
  /** 三态：true 成功 / false 失败 / null 进行中（请求已发出、尚未返回） */
  ok: boolean | null
  error_kind: string | null
  error_detail: string | null
  request_messages: LlmCallMessage[]
  response_text: string | null
  latency_ms: number | null
  usage: Record<string, unknown> | null
}

/** `GET /ai/calls` 的 limit/offset 形状——与 `Paginated`（page/page_size）不同，勿复用。 */
export interface LlmCallPage {
  total: number
  items: LlmCallRow[]
}

export interface SuppressionRow {
  id: number
  scope: 'email' | 'phone' | 'contact' | 'company' | 'domain'
  target_value: string
  reason: 'unsubscribed' | 'bounced' | 'manual' | 'complaint' | 'invalid'
  company_id: number | null
  contact_id: number | null
  source: string | null
  note: string | null
  created_at: string | null
}

// ---- AI 提示词（006；contracts/prompt-customization-contract.md §1~§5，模板库版） ----

export type PromptFeatureKey = 'seed_expand' | 'content_draft'

export interface PromptVariable {
  name: string
  label: string
  /** 渲染语义说明（"将被替换为…"），直接展示给用户 */
  render: string
}

export interface PromptTemplateSummary {
  feature: PromptFeatureKey
  label: string
  customized: boolean
  active_id: string | null
  active_name: string | null
  template_count: number
}

export interface PromptWarning {
  code: string
  message: string
}

export interface PromptTemplateItem {
  id: string
  name: string
  content: string
  updated_at: string | null
}

export interface PromptTemplateDetail {
  feature: PromptFeatureKey
  label: string
  default_content: string
  /** null = 生效为内置默认 */
  active_id: string | null
  active_name: string | null
  customized: boolean
  max_length: number
  max_name_length: number
  max_templates: number
  templates: PromptTemplateItem[]
  variables: PromptVariable[]
  reserved_variables: PromptVariable[]
  output_contract: string
  /** 仅写入类响应（创建/更新）携带：不阻断保存的警告（contract §7 码表） */
  warnings?: PromptWarning[]
}

export interface PromptAssistResponse {
  suggestion: string
  notes: string | null
}
