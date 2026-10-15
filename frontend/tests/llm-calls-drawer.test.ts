/**
 * T267 LLM 调用明细抽屉（红→绿）：请求参数、入参/出参渲染、修复链合卡、失败详情、
 * 耗时/用量、空态、翻页、加载失败重试、复制、默认展开。
 * 契约：GET /ai/calls?job_id=&limit=&offset= → {total, items[]}（local-api.md）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import { i18n } from '../src/i18n'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
  sseUrl: (path: string) => path,
}))

import { api } from '../src/api/client'
import type { LlmCallPage, LlmCallRow } from '../src/api/types'
import LlmCallsDrawer from '../src/components/common/LlmCallsDrawer.vue'

const get = vi.mocked(api.get)

type OpenOptions = { jobId?: number; operation?: string; title?: string }

function row(overrides: Partial<LlmCallRow> = {}): LlmCallRow {
  return {
    id: 1,
    ts: '2026-10-15T01:59:54.580502',
    job_id: 9,
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

function page(items: LlmCallRow[], total = items.length): LlmCallPage {
  return { total, items }
}

/** 挂载抽屉并按给定响应打开（响应函数每次请求都会重新求值，便于测重试/翻页）。 */
async function mountAndOpen(
  respond: () => Promise<LlmCallPage>,
  options: OpenOptions = { jobId: 9 },
) {
  get.mockImplementation((path: string) => {
    if (path === '/ai/calls') return respond()
    return Promise.reject(new Error(`unexpected path ${path}`))
  })
  const wrapper = mount(LlmCallsDrawer, {
    global: { plugins: [ElementPlus, i18n] },
    attachTo: document.body,
  })
  await flushPromises()
  return { wrapper, open: (opts: OpenOptions = options) => { (wrapper.vm as unknown as { open: (o: OpenOptions) => void }).open(opts) } }
}

const ok =
  (items: LlmCallRow[], total?: number) =>
  () =>
    Promise.resolve(page(items, total))

function drawerEl(): HTMLElement {
  return document.body.querySelector('.llm-calls-drawer') as HTMLElement
}

function calls(): HTMLElement[] {
  return [...document.body.querySelectorAll<HTMLElement>('[data-test="llm-call"]')]
}

beforeEach(() => {
  document.body.innerHTML = ''
  get.mockReset()
})

describe('LlmCallsDrawer · 数据加载', () => {
  it('按任务拉取调用明细（limit/offset 分页）；未打开不渲染，标题可见', async () => {
    const { open } = await mountAndOpen(ok([row()]))
    // EP 抽屉根元素常驻 DOM（v-show），但正文懒渲染——打开前不应有内容
    expect(document.body.querySelector('.llm-calls-body')).toBeNull()

    open({ jobId: 9 })
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/ai/calls', { job_id: 9, limit: 20, offset: 0 })
    expect(drawerEl().textContent).toContain('AI 调用明细')
  })

  it('无调用记录时呈现空态', async () => {
    const { open } = await mountAndOpen(ok([]))
    open()
    await flushPromises()
    expect(drawerEl().textContent).toContain('暂无调用记录')
  })

  it('加载失败给出错误块并可重试', async () => {
    let failing = true
    const { open } = await mountAndOpen(() =>
      failing ? Promise.reject(new Error('boom')) : Promise.resolve(page([row({ response_text: 'RAW-OUTPUT' })]))
    )
    open()
    await flushPromises()
    expect(document.body.querySelector('[data-test="llm-load-error"]')).not.toBeNull()

    failing = false
    ;(document.body.querySelector('[data-test="llm-retry"]') as HTMLElement).click()
    await flushPromises()
    expect(drawerEl().textContent).toContain('RAW-OUTPUT')
  })

  it('超过一页显示分页，翻页按 offset 增量请求', async () => {
    const { open } = await mountAndOpen(ok([row()], 45))
    open()
    await flushPromises()

    const next = drawerEl().querySelector<HTMLElement>('.btn-next')
    expect(next).not.toBeNull()
    next!.click()
    await flushPromises()
    expect(get).toHaveBeenLastCalledWith('/ai/calls', { job_id: 9, limit: 20, offset: 20 })
  })

  it('不足一页不显示分页', async () => {
    const { open } = await mountAndOpen(ok([row()], 3))
    open()
    await flushPromises()
    expect(drawerEl().querySelector('.el-pagination')).toBeNull()
  })
})

describe('LlmCallsDrawer · 内容呈现', () => {
  it('渲染入参（system/user 全文）与出参原文', async () => {
    const { open } = await mountAndOpen(
      ok([
        row({
          request_messages: [
            { role: 'system', content: 'SYS-PROMPT' },
            { role: 'user', content: 'USER-PROMPT' },
          ],
          response_text: 'RAW-OUTPUT',
        }),
      ]),
    )
    open()
    await flushPromises()

    const text = drawerEl().textContent ?? ''
    expect(text).toContain('SYS-PROMPT')
    expect(text).toContain('USER-PROMPT')
    expect(text).toContain('RAW-OUTPUT')
    expect(text).toContain('系统')
    expect(text).toContain('用户')
  })

  it('同一 call_index 的修复重试合成一张卡，尝试升序展示', async () => {
    const { open } = await mountAndOpen(
      ok([
        row({
          id: 12,
          attempt: 2,
          request_messages: [
            { role: 'user', content: 'USER-PROMPT' },
            { role: 'assistant', content: 'BAD-JSON-1' },
            { role: 'user', content: '请返回修正后的严格 JSON' },
          ],
          response_text: 'FIXED',
        }),
        row({ id: 11, attempt: 1, ok: false, response_text: 'NOT-JSON' }),
      ]),
    )
    open()
    await flushPromises()

    expect(calls()).toHaveLength(1)
    const attempts = calls()[0].querySelectorAll<HTMLElement>('[data-test="llm-attempt"]')
    expect(attempts).toHaveLength(2)
    expect(attempts[0].textContent).toContain('NOT-JSON')
    expect(attempts[1].textContent).toContain('BAD-JSON-1')
  })

  it('失败尝试显示错误类别与详情，无输出不崩', async () => {
    const { open } = await mountAndOpen(
      ok([
        row({
          ok: false,
          response_text: null,
          error_kind: 'network',
          error_detail: "TypeError: 'NoneType' object is not subscriptable",
        }),
      ]),
    )
    open()
    await flushPromises()

    const text = drawerEl().textContent ?? ''
    expect(text).toContain('失败')
    expect(text).toContain('network')
    expect(text).toContain("'NoneType' object is not subscriptable")
    expect(text).toContain('（无输出）')
  })

  it('显示每次尝试的耗时与 token 用量', async () => {
    const { open } = await mountAndOpen(
      ok([
        row({
          latency_ms: 84_000,
          usage: { prompt_tokens: 100, completion_tokens: 50, total_tokens: 150 },
        }),
      ]),
    )
    open()
    await flushPromises()

    const text = drawerEl().textContent ?? ''
    expect(text).toContain('1m24s')
    expect(text).toContain('输入 100 · 输出 50 · 合计 150 tokens')
  })

  it('默认只展开最新一次调用，其余点击后展开', async () => {
    const { open } = await mountAndOpen(
      ok([
        row({ id: 2, call_index: 2, response_text: 'NEWEST' }),
        row({ id: 1, call_index: 1, response_text: 'OLDEST' }),
      ]),
    )
    open()
    await flushPromises()

    expect(calls()[0].textContent).toContain('NEWEST')
    expect(calls()[1].querySelector('[data-test="llm-attempt"]')).toBeNull()

    ;(calls()[1].querySelector('[data-test="llm-call-head"]') as HTMLElement).click()
    await flushPromises()
    expect(calls()[1].textContent).toContain('OLDEST')
  })

  it('复制出参到剪贴板', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const { open } = await mountAndOpen(ok([row({ response_text: 'RAW-OUTPUT' })]))
    open()
    await flushPromises()

    ;(document.body.querySelector('[data-test="copy-output"]') as HTMLElement).click()
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('RAW-OUTPUT')
  })
})
