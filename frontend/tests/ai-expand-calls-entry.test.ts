/**
 * T269/T271 迁移（T239）：AI 扩充对话框改由任务中心 store 驱动（register/waitFor + SSE），
 * 保留原行为——任务完成（成功或失败）后「查看调用明细」入口按 job_id 打开 T267 明细抽屉、
 * 不关闭对话框；调用中「已等待」时长随 1s tick 可见。
 * T286（006）：提示词入口 + 默认/已自定义徽标 + 以 seed_expand 打开编辑器 + 保存后徽标刷新。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import { i18n } from '../src/i18n'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
  sseUrl: (path: string) => path,
}))

import { api } from '../src/api/client'
import type { JobPayload, PromptTemplateDetail } from '../src/api/types'
import { useJobCenterStore } from '../src/stores/jobCenter'
import AiExpandDialog from '../src/views/seeds/AiExpandDialog.vue'
import PromptEditorDialog from '../src/components/common/PromptEditorDialog.vue'

const get = vi.mocked(api.get)
const post = vi.mocked(api.post)

/** 每用例独立 pinia（订阅表为 store 模块级，以 init() 清空重建，防跨用例残留） */
let pinia: Pinia

class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  closed = false
  private listeners: Record<string, Array<(ev: MessageEvent) => void>> = {}

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, cb: (ev: MessageEvent) => void) {
    ;(this.listeners[type] ||= []).push(cb)
  }

  close() {
    this.closed = true
  }

  emit(type: string, data?: unknown) {
    const ev = { data: data === undefined ? '' : JSON.stringify(data) } as MessageEvent
    for (const cb of this.listeners[type] ?? []) cb(ev)
  }

  static find(url: string): FakeEventSource {
    const found = FakeEventSource.instances.find((item) => item.url === url)
    if (!found) throw new Error(`未找到 EventSource：${url}`)
    return found
  }
}

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

async function openDialog(pinia: Pinia) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/seeds/review', component: { template: '<div />' } },
    ],
  })
  const wrapper = mount(AiExpandDialog, {
    global: { plugins: [pinia, ElementPlus, router, i18n] },
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
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  get.mockImplementation((path: string) => {
    if (path === '/graph/nodes') {
      return Promise.resolve({ items: [], total: 0, page: 1, page_size: 500 })
    }
    if (path === '/ai/calls') return Promise.resolve({ total: 0, items: [] })
    return Promise.reject(new Error(`unexpected path ${path}`))
  })
  post.mockResolvedValue({ job_id: 7 })
  pinia = createPinia()
  setActivePinia(pinia)
  void useJobCenterStore()
    .init()
    .catch(() => undefined)
})

describe('AiExpandDialog · 查看调用明细入口（T269，store 驱动）', () => {
  it('提交前无入口；成功后出现，点击按 job_id 打开明细且不关闭对话框', async () => {
    let detailCalls = 0
    get.mockImplementation((path: string) => {
      if (path === '/graph/nodes') {
        return Promise.resolve({ items: [], total: 0, page: 1, page_size: 500 })
      }
      if (path === '/ai/calls') return Promise.resolve({ total: 0, items: [] })
      if (path === '/jobs/7') {
        detailCalls += 1
        return Promise.resolve(
          jobPayload({ status: detailCalls === 1 ? 'running' : 'completed' }),
        )
      }
      return Promise.reject(new Error(`unexpected path ${path}`))
    })
    await openDialog(pinia)
    expect(document.body.querySelector('[data-test="expand-view-calls"]')).toBeNull()

    await clickSubmit()
    // 提交即登记：建立既有 /jobs/{id}/events 订阅（唯一订阅方）
    FakeEventSource.find('/jobs/7/events').emit('done', { result: { nodes_created: 1 } })
    await flushPromises()

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
    let detailCalls = 0
    get.mockImplementation((path: string) => {
      if (path === '/graph/nodes') {
        return Promise.resolve({ items: [], total: 0, page: 1, page_size: 500 })
      }
      if (path === '/jobs/7') {
        detailCalls += 1
        return Promise.resolve(
          jobPayload({
            status: detailCalls === 1 ? 'running' : 'failed',
            result: null,
            error: 'ProviderError: boom',
          }),
        )
      }
      return Promise.reject(new Error(`unexpected path ${path}`))
    })
    await openDialog(pinia)
    await clickSubmit()
    FakeEventSource.find('/jobs/7/events').emit('error', { code: 'job_failed', message: '任务失败' })
    await flushPromises()
    expect(document.body.querySelector('[data-test="expand-view-calls"]')).not.toBeNull()
  })
})

describe('AiExpandDialog · 提示词入口（T286，006）', () => {
  function promptDetail(): PromptTemplateDetail {
    return {
      feature: 'seed_expand',
      label: 'AI 扩充（种子扩充）',
      default_content: '你是助手。\n{description}\n{existing_nodes}\n{output_contract}\n约 {count} 条。',
      active_id: null,
      active_name: null,
      customized: false,
      max_length: 8000,
      max_name_length: 60,
      max_templates: 50,
      templates: [],
      variables: [
        { name: 'description', label: '业务描述', render: '有值 →「业务描述：…」' },
        { name: 'existing_nodes', label: '已有节点名单', render: '逐行' },
        { name: 'count', label: '候选数量', render: '纯数字' },
      ],
      reserved_variables: [
        { name: 'output_contract', label: '输出结构槽位', render: '替换为固定段原文' },
      ],
      output_contract: '输出 JSON，结构：…',
    }
  }

  function mockPromptApis(customized: boolean, activeName: string | null = null) {
    get.mockImplementation((path: string) => {
      if (path === '/graph/nodes') {
        return Promise.resolve({ items: [], total: 0, page: 1, page_size: 500 })
      }
      if (path === '/ai/prompts') {
        return Promise.resolve({
          items: [
            {
              feature: 'seed_expand',
              label: 'AI 扩充（种子扩充）',
              customized,
              active_id: customized ? 't_a' : null,
              active_name: customized ? activeName : null,
              template_count: customized ? 1 : 0,
            },
            {
              feature: 'content_draft',
              label: 'AI 起草（内容母版）',
              customized: false,
              active_id: null,
              active_name: null,
              template_count: 0,
            },
          ],
        })
      }
      if (path === '/ai/prompts/seed_expand') return Promise.resolve(promptDetail())
      return Promise.reject(new Error(`unexpected path ${path}`))
    })
  }

  function entry(): HTMLElement | null {
    return document.body.querySelector<HTMLElement>('[data-test="expand-prompt-entry"]')
  }

  function badge(): HTMLElement | null {
    return document.body.querySelector<HTMLElement>('[data-test="expand-prompt-badge"]')
  }

  it('表单态出现入口与「默认」徽标', async () => {
    mockPromptApis(false)
    await openDialog(pinia)
    expect(entry()).not.toBeNull()
    expect(entry()!.textContent).toContain('提示词')
    expect(entry()!.textContent).toContain('默认')
  })

  it('已自定义：徽标显示生效模板名（T300 升级）', async () => {
    mockPromptApis(true, '东非市场')
    await openDialog(pinia)
    expect(entry()!.textContent).toContain('东非市场')
    expect(entry()!.textContent).not.toContain('已自定义')
  })

  it('徽标取数失败：入口仍在、徽标不显示（不打断）', async () => {
    get.mockImplementation((path: string) => {
      if (path === '/graph/nodes') {
        return Promise.resolve({ items: [], total: 0, page: 1, page_size: 500 })
      }
      return Promise.reject(new Error(`unexpected path ${path}`))
    })
    await openDialog(pinia)
    expect(entry()).not.toBeNull()
    expect(badge()).toBeNull()
  })

  it('点击入口以 seed_expand 打开编辑器', async () => {
    mockPromptApis(false)
    await openDialog(pinia)
    entry()!.click()
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/ai/prompts/seed_expand')
    expect(document.body.textContent).toContain('AI 提示词 · AI 扩充（种子扩充）')
  })

  it('编辑器 changed 回调后徽标刷新（默认 → 模板名）', async () => {
    mockPromptApis(false)
    const wrapper = await openDialog(pinia)
    entry()!.click()
    await flushPromises()
    mockPromptApis(true, '东非市场') // 保存后服务端状态切换
    wrapper.findComponent(PromptEditorDialog).vm.$emit('changed', 'seed_expand')
    await flushPromises()
    expect(entry()!.textContent).toContain('东非市场')
  })

  it('进行中面板态（panelMode）不出现入口', async () => {
    mockPromptApis(false)
    const store = useJobCenterStore()
    store.activeJobs[9] = jobPayload({ id: 9, status: 'running', result: null })
    const wrapper = mount(AiExpandDialog, {
      global: {
        plugins: [
          pinia,
          ElementPlus,
          createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] }),
          i18n,
        ],
      },
      attachTo: document.body,
    })
    await (wrapper.vm as unknown as { open: () => Promise<void> }).open()
    await flushPromises()
    expect(document.body.textContent).toContain('关闭本窗口不会中断任务')
    expect(entry()).toBeNull()
  })
})

describe('AiExpandDialog · 调用中「已等待」（T271，store 驱动）', () => {
  it('订阅到 running 时进度文案带已等待时长——前台卡住也知道等了多久', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-15T02:00:24Z'))
    let detailCalls = 0
    get.mockImplementation((path: string) => {
      if (path === '/graph/nodes') {
        return Promise.resolve({ items: [], total: 0, page: 1, page_size: 500 })
      }
      if (path === '/jobs/7') {
        detailCalls += 1
        // 收尾后详情补齐返回终态（真实服务端语义）；首查为 running
        return Promise.resolve(
          jobPayload({ status: detailCalls === 1 ? 'running' : 'completed', result: {} }),
        )
      }
      return Promise.reject(new Error(`unexpected path ${path}`))
    })
    try {
      await openDialog(pinia)
      await clickSubmit()
      FakeEventSource.find('/jobs/7/events').emit('progress', {
        snapshot: jobPayload({
          status: 'running',
          progress: { phase: 'calling_llm' },
          started_at: '2026-10-15T01:59:54.000000',
        }),
      })
      await vi.advanceTimersByTimeAsync(1000)
      const text = document.body.textContent ?? ''
      expect(text).toContain('大模型正在生成候选')
      // tick 前进 1s 后读表：01:59:54 → 02:00:25 = 31s（旧轮询在 emit 时刻即为 30s）
      expect(text).toContain('已等待 31 秒')

      FakeEventSource.find('/jobs/7/events').emit('done', { result: {} }) // 收尾：任务完成
      await flushPromises()
      expect(document.body.textContent).toContain('已完成')
    } finally {
      vi.useRealTimers()
    }
  })
})
