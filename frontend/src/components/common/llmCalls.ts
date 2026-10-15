/**
 * LLM 调用明细（T267）展示口径：修复链分组与耗时/时间/用量/标签格式化。
 *
 * 接口按 id 倒序（新→旧），一次调用的修复重试（attempt>1）是独立行——展示时按
 * (job_id, call_index) 合成一张卡，组内按 attempt 升序。分页单位是行：修复链
 * 恰好跨页时会断成两卡（limit=20 下影响可忽略，已知限制）。
 * 服务端时间为朴素 UTC（无时区后缀），一律经 `parseServerTime` 解析。
 */

import type { LlmCallRow } from '../../api/types'
import { langLabel } from '../../constants'
import { parseServerTime } from '../../stores/jobCenter'

export interface LlmCallGroup {
  key: string
  jobId: number | null
  callIndex: number
  operation: string
  phase: string | null
  provider: string
  model: string
  /** 各次尝试（升序） */
  attempts: LlmCallRow[]
  /** 末次尝试是否成功（修复链以最后一次为准） */
  ok: boolean
  /** 末次尝试的错误类别（成功为 null） */
  errorKind: string | null
  /** 各次尝试耗时求和（null 不计入） */
  totalLatencyMs: number
  /** 首次尝试时间（朴素 UTC） */
  ts: string | null
}

export function groupAttempts(rows: LlmCallRow[]): LlmCallGroup[] {
  const groups = new Map<string, LlmCallGroup>()
  for (const row of rows) {
    const key = `${row.job_id ?? 'none'}:${row.call_index}`
    let group = groups.get(key)
    if (!group) {
      group = {
        key,
        jobId: row.job_id,
        callIndex: row.call_index,
        operation: row.operation,
        phase: row.phase,
        provider: row.provider,
        model: row.model,
        attempts: [],
        ok: row.ok,
        errorKind: row.error_kind,
        totalLatencyMs: 0,
        ts: row.ts,
      }
      groups.set(key, group)
    }
    group.attempts.push(row)
  }
  for (const group of groups.values()) {
    group.attempts.sort((a, b) => a.attempt - b.attempt)
    const last = group.attempts[group.attempts.length - 1]
    group.ok = last.ok
    group.errorKind = last.error_kind
    group.totalLatencyMs = group.attempts.reduce((sum, item) => sum + (item.latency_ms ?? 0), 0)
    group.ts = group.attempts[0].ts
  }
  return [...groups.values()]
}

export function formatLatency(ms: number | null | undefined): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const minutes = Math.floor(ms / 60_000)
  const seconds = Math.round((ms % 60_000) / 1000)
  return `${minutes}m${seconds}s`
}

export function formatTs(ts: string | null | undefined): string {
  const timestamp = parseServerTime(ts)
  if (timestamp == null) return '—'
  const date = new Date(timestamp)
  const pad = (value: number) => String(value).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  )
}

/** 消息内容口径：字符串原样；其余（多段 content 等）JSON 化展示。 */
export function messageText(content: unknown): string {
  if (typeof content === 'string') return content
  if (content == null) return ''
  return JSON.stringify(content, null, 2) ?? ''
}

const USAGE_FIELDS: Array<{ key: string; label: string }> = [
  { key: 'prompt_tokens', label: '输入' },
  { key: 'completion_tokens', label: '输出' },
  { key: 'total_tokens', label: '合计' },
]

export function usageText(usage: Record<string, unknown> | null | undefined): string {
  if (!usage) return '用量未记录'
  const parts = USAGE_FIELDS.filter(({ key }) => typeof usage[key] === 'number').map(
    ({ key, label }) => `${label} ${usage[key]}`,
  )
  return parts.length ? `${parts.join(' · ')} tokens` : '用量未记录'
}

export const OPERATION_LABELS: Record<string, string> = {
  seed_expand: '种子扩充',
  seed_translate: '种子翻译',
  term_translate: '术语翻译',
  content_draft: '内容起草',
  content_translate: '内容翻译',
}

export function operationLabel(operation: string): string {
  return OPERATION_LABELS[operation] ?? operation
}

export const ROLE_LABELS: Record<string, string> = {
  system: '系统',
  user: '用户',
  assistant: '模型',
  tool: '工具',
}

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role
}

/** 多语言任务用 `lang:<code>` 标注每次调用的上下文（ai_translate.py）；其余原样。 */
export function phaseText(phase: string | null | undefined): string {
  if (!phase) return ''
  if (phase.startsWith('lang:')) return `语言 ${langLabel(phase.slice(5))}`
  return phase
}
