/**
 * 回归测试（红→绿）：启动挖掘任务的数值参数必须可输入。
 *
 * 缺陷背景：并发 / 单站间隔（秒）/ 单站页数 原为「el-col span=8 + 左侧 label（120px）」的
 * 三数列，列内可用宽度（~84px）远小于 el-input-number 的固定宽（150px）；flex 压缩后
 * 内部 <input> 的可用宽度塌缩为 0（真机 CDP 实测 inputW=0px），数值不可见、也无法键入。
 * 契约：紧凑数列中的数值控件必须 label 置顶、控件撑满列宽——这是「输入区不被压缩」的
 * jsdom 可断言前提（真正的像素验收走 headless Chrome CDP）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import { api } from '../src/api/client'
import CrawlJobs from '../src/views/leads/CrawlJobs.vue'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
  sseUrl: (path: string) => path,
}))

const mockedApi = vi.mocked(api)

function stubApi() {
  mockedApi.get.mockImplementation(async (path: string) => {
    if (path === '/crawl/jobs') return { items: [], total: 0, page: 1, page_size: 50 }
    if (path === '/seeds') return { items: [], total: 0, page: 1, page_size: 200 }
    return {}
  })
}

async function openStartDialog(): Promise<VueWrapper> {
  const wrapper = mount(CrawlJobs, {
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await flushPromises()
  const startBtn = wrapper.findAll('button').find((b) => b.text().includes('启动挖掘'))
  expect(startBtn).toBeTruthy()
  await startBtn!.trigger('click')
  await flushPromises()
  return wrapper
}

function paramItem(label: string): HTMLElement {
  const items = [...document.querySelectorAll<HTMLElement>('.el-dialog .el-form-item')]
  const item = items.find(
    (el) => el.querySelector('.el-form-item__label')?.textContent?.trim() === label,
  )
  expect(item, `未找到参数「${label}」`).toBeTruthy()
  return item!
}

describe('启动挖掘任务 · 数值参数可输入', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
    stubApi()
  })

  it.each(['并发', '单站间隔（秒）', '单站页数'])(
    '参数「%s」：label 置顶且控件撑满列宽（输入区不被压缩）',
    async (label) => {
      await openStartDialog()
      const item = paramItem(label)
      // 1) label 置顶：不占用列内水平空间（列宽已不足以同时容纳左 label 与 150px 控件）
      expect(item.classList.contains('el-form-item--label-top')).toBe(true)
      // 2) 控件撑满列宽：内部 <input> 才有可用宽度（固定 150px 在窄列中会被压成 0）
      const number = item.querySelector<HTMLElement>('.el-input-number')
      expect(number, `参数「${label}」缺少 el-input-number`).toBeTruthy()
      expect(number!.style.width).toBe('100%')
    },
  )

  it('三个参数仍为数值控件且绑定默认值（并发 5 / 间隔 1 / 页数 6）', async () => {
    await openStartDialog()
    const values = [paramItem('并发'), paramItem('单站间隔（秒）'), paramItem('单站页数')].map(
      (item) => item.querySelector('input')?.value,
    )
    expect(values).toEqual(['5', '1', '6'])
  })
})
