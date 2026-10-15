/**
 * T267 LLM 调用明细（红→绿）：展示用纯函数——修复链合卡分组与耗时/时间/用量/标签格式化。
 * 数据源：GET /ai/calls（contracts/local-api.md；llm_call 表 data-model E7）。
 */

import { describe, expect, it } from 'vitest'

import type { LlmCallRow } from '../src/api/types'
import {
  formatLatency,
  formatTs,
  groupAttempts,
  messageText,
  operationLabel,
  phaseText,
  roleLabel,
  usageText,
} from '../src/components/common/llmCalls'

function row(overrides: Partial<LlmCallRow> = {}): LlmCallRow {
  return {
    id: 1,
    ts: '2026-10-15T01:59:54.580502',
    job_id: 7,
    call_index: 1,
    phase: null,
    operation: 'seed_expand',
    provider: 'DeepSeek',
    model: 'deepseek-chat',
    attempt: 1,
    ok: true,
    error_kind: null,
    error_detail: null,
    request_messages: [{ role: 'user', content: 'hi' }],
    response_text: '{}',
    latency_ms: 1000,
    usage: null,
    ...overrides,
  }
}

describe('groupAttempts · 修复链合卡', () => {
  it('同 (job_id, call_index) 归一组；组内 attempt 升序；组保持新→旧', () => {
    const groups = groupAttempts([
      row({ id: 3, call_index: 1, attempt: 2 }),
      row({ id: 2, call_index: 1, attempt: 1, ok: false }),
      row({ id: 1, call_index: 2, attempt: 1 }),
    ])
    expect(groups.map((group) => group.callIndex)).toEqual([1, 2])
    expect(groups[0].attempts.map((item) => item.attempt)).toEqual([1, 2])
  })

  it('不同任务的同序号调用不合并（组键含 job_id）', () => {
    const groups = groupAttempts([
      row({ id: 2, job_id: 8, call_index: 1 }),
      row({ id: 1, job_id: 7, call_index: 1 }),
    ])
    expect(groups).toHaveLength(2)
  })

  it('汇总：末次尝试状态、各次耗时求和、时间为首次尝试时间', () => {
    const [group] = groupAttempts([
      row({ id: 2, attempt: 2, ok: false, latency_ms: 500, ts: '2026-10-15T02:00:05' }),
      row({ id: 1, attempt: 1, ok: false, latency_ms: 902219, ts: '2026-10-15T01:59:54' }),
    ])
    expect(group.ok).toBe(false)
    expect(group.totalLatencyMs).toBe(902719)
    expect(group.ts).toBe('2026-10-15T01:59:54')
  })

  it('耗时缺失的尝试不计入总耗时', () => {
    const [group] = groupAttempts([row({ id: 2, attempt: 2, latency_ms: null }), row({ id: 1 })])
    expect(group.totalLatencyMs).toBe(1000)
  })
})

describe('formatLatency · 耗时口径', () => {
  it.each([
    [null, '—'],
    [420, '420ms'],
    [1234, '1.2s'],
    [60_000, '1m0s'],
    [84_000, '1m24s'],
    [902_219, '15m2s'],
  ])('%s → %s', (value, expected) => {
    expect(formatLatency(value)).toBe(expected)
  })
})

describe('formatTs · 服务端时间为朴素 UTC', () => {
  it('无时区后缀按 UTC 解析并以本地时间展示', () => {
    const naive = '2026-10-14T05:45:34.740728'
    const date = new Date(`${naive}Z`)
    const pad = (value: number) => String(value).padStart(2, '0')
    const expected =
      `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
      `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
    expect(formatTs(naive)).toBe(expected)
  })

  it('带 Z 后缀与不带后缀解析为同一时刻；null → —', () => {
    const naive = '2026-10-14T05:45:34.740728'
    expect(formatTs(naive)).toBe(formatTs(`${naive}Z`))
    expect(formatTs(null)).toBe('—')
  })
})

describe('messageText / usageText · 明细内容口径', () => {
  it('文本原样；非字符串内容 JSON 化；空值空串', () => {
    expect(messageText('原始文本')).toBe('原始文本')
    expect(messageText(null)).toBe('')
    expect(messageText([{ type: 'text', text: 'hi' }])).toBe(
      JSON.stringify([{ type: 'text', text: 'hi' }], null, 2),
    )
  })

  it('token 用量：完整/部分/未知/缺失', () => {
    expect(usageText({ prompt_tokens: 100, completion_tokens: 50, total_tokens: 150 })).toBe(
      '输入 100 · 输出 50 · 合计 150 tokens',
    )
    expect(usageText({ total_tokens: 12 })).toBe('合计 12 tokens')
    expect(usageText({ mystery: 1 })).toBe('用量未记录')
    expect(usageText(null)).toBe('用量未记录')
  })
})

describe('标签口径', () => {
  it.each([
    ['seed_expand', '种子扩充'],
    ['seed_translate', '种子翻译'],
    ['term_translate', '术语翻译'],
    ['content_draft', '内容起草'],
    ['content_translate', '内容翻译'],
    ['mystery', 'mystery'],
  ])('operationLabel(%s) → %s', (value, expected) => {
    expect(operationLabel(value)).toBe(expected)
  })

  it.each([
    ['system', '系统'],
    ['user', '用户'],
    ['assistant', '模型'],
    ['other', 'other'],
  ])('roleLabel(%s) → %s', (value, expected) => {
    expect(roleLabel(value)).toBe(expected)
  })

  it('phase：多语言任务标注语言，其余原样，空值空串', () => {
    expect(phaseText('lang:en')).toBe('语言 英语')
    expect(phaseText('lang:xx')).toBe('语言 xx')
    expect(phaseText('calling_llm')).toBe('calling_llm')
    expect(phaseText(null)).toBe('')
  })
})
