/**
 * T269 AI 扩充对话框完成后「查看调用明细」入口（红→绿）：
 * 任务完成（成功或失败）后按 job_id 打开 T267 明细抽屉，且不关闭对话框。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'

import { i18n } from '../src/i18n'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
  sseUrl: (path: string) => path,
}))

vi.mock('../src/api/jobs', () => ({ watchJob: vi.fn() }))

import { api } from '../src/api/client'
import { watchJob } from '../src/api/jobs'
import type { JobPayload } from '../src/api/types'
import AiExpandDialog from '../src/views/seeds/AiExpandDialog.vue'

const get = vi.mocked(api.get)
const post = vi.mocked(api.post)
const waitJob = vi.mocked(watchJob)

function jobPayload(overrides: Partial<JobPayload> = {}): JobPayload {
  return {
    id: 7,
    job_type: 'ai_seed_expand',
    name: 'AI 扩充种子',
    status: 'completed',
    progress: {},
    result: { nodes_created: 1 },
    error: null,
    ref_type: null,
    ref_id: null,
    created_at: null,
    started_at: null,
    finished_at: null,
    can_pause: false,
    rerunnable: false,
    ...overrides,
  }
}

async function openDialog() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/seeds/review', component: { template: '<div />' } },
    ],
  })
  const wrapper = mount(AiExpandDialog, {
    global: { plugins: [ElementPlus, router, i18n] },
    attachTo: document.body,
  })
  await flushPromises()
  await (wrapper.vm as unknown as { open: () => Promise<void> }).open()
  await flushPromises()

  const textarea = document.body.querySelector<HTMLTextAreaElement>('.el-textarea__inner')!
  textarea.value = '电力金具出口'
  textarea.dispatchEvent(new Event('input'))
  await flushPromises()
  return wrapper
}

async function clickSubmit() {
  const submit = [...document.body.querySelectorAll<HTMLElement>('button')].find(
    (button) => button.textContent?.trim() === '开始扩充',
  )!
  submit.click()
  await flushPromises()
}

beforeEach(() => {
  document.body.innerHTML = ''
  get.mockReset()
  post.mockReset()
  waitJob.mockReset()
  get.mockImplementation((path: string) => {
    if (path === '/graph/nodes') {
      return Promise.resolve({ items: [], total: 0, page: 1, page_size: 500 })
    }
    if (path === '/ai/calls') return Promise.resolve({ total: 0, items: [] })
    return Promise.reject(new Error(`unexpected path ${path}`))
  })
  post.mockResolvedValue({ job_id: 7 })
})

describe('AiExpandDialog · 查看调用明细入口（T269）', () => {
  it('提交前无入口；成功后出现，点击按 job_id 打开明细且不关闭对话框', async () => {
    waitJob.mockResolvedValue(jobPayload())
    await openDialog()
    expect(document.body.querySelector('[data-test="expand-view-calls"]')).toBeNull()

    await clickSubmit()
    const entry = document.body.querySelector<HTMLElement>('[data-test="expand-view-calls"]')
    expect(entry).not.toBeNull()

    entry!.click()
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/ai/calls', { job_id: 7, limit: 20, offset: 0 })
    expect(document.body.querySelector('.llm-calls-drawer')?.textContent).toContain('AI 调用明细')
    // 对话框保持打开（明细叠在其上）
    expect(document.body.querySelector('.el-dialog')?.textContent).toContain('AI 知识图谱扩充')
  })

  it('任务失败后入口仍出现（失败时最需要看明细）', async () => {
    waitJob.mockResolvedValue(jobPayload({ status: 'failed', result: null, error: 'ProviderError: boom' }))
    await openDialog()
    await clickSubmit()
    expect(document.body.querySelector('[data-test="expand-view-calls"]')).not.toBeNull()
  })
})

describe('AiExpandDialog · 调用中「已等待」（T271）', () => {
  it('轮询到 running 时进度文案带已等待时长——前台卡住也知道等了多久', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-15T02:00:24Z'))
    let resolveJob!: (job: JobPayload) => void
    waitJob.mockImplementation((_jobId, onTick) => {
      onTick?.(
        jobPayload({
          status: 'running',
          progress: { phase: 'calling_llm' },
          started_at: '2026-10-15T01:59:54.000000',
        }),
      )
      return new Promise<JobPayload>((resolve) => {
        resolveJob = resolve
      })
    })
    try {
      await openDialog()
      await clickSubmit()
      const text = document.body.textContent ?? ''
      expect(text).toContain('大模型正在生成候选')
      expect(text).toContain('已等待 30 秒')

      resolveJob(jobPayload()) // 收尾：任务完成
      await flushPromises()
      expect(document.body.textContent).toContain('已完成')
    } finally {
      vi.useRealTimers()
    }
  })
})
