/**
 * 回归测试（红→绿）：通道对话框「发送限制」三个数值参数必须可输入。
 *
 * 与启动挖掘任务同源缺陷：每日上限 / 条每分钟 / 并发 原为「el-col span=8 + 左侧 label」，
 * 列内可用宽度（~94~118px）被 flex 压缩后，el-input-number 内部 <input> 仅剩 14~34px，
 * 数值不可读、无法键入（真机 CDP 实测）。契约同 crawl-job-params：label 置顶 + 控件撑满列宽。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import { api } from '../src/api/client'
import ChannelForm from '../src/views/channels/ChannelForm.vue'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
  sseUrl: (path: string) => path,
}))

const mockedApi = vi.mocked(api)

async function openCreateDialog(): Promise<VueWrapper> {
  const wrapper = mount(ChannelForm, {
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await flushPromises()
  const vm = wrapper.vm as unknown as { open: (channel: null, manifests: unknown[]) => void }
  vm.open(null, [])
  await flushPromises()
  return wrapper
}

function limitItem(label: string): HTMLElement {
  const items = [...document.querySelectorAll<HTMLElement>('.el-dialog .el-form-item')]
  const item = items.find(
    (el) => el.querySelector('.el-form-item__label')?.textContent?.trim() === label,
  )
  expect(item, `未找到参数「${label}」`).toBeTruthy()
  return item!
}

describe('发送通道 · 发送限制数值参数可输入', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
    mockedApi.get.mockResolvedValue({ items: [], total: 0 })
  })

  it.each(['每日上限', '条/分钟', '并发'])(
    '参数「%s」：label 置顶且控件撑满列宽（输入区不被压缩）',
    async (label) => {
      await openCreateDialog()
      const item = limitItem(label)
      expect(item.classList.contains('el-form-item--label-top')).toBe(true)
      const number = item.querySelector<HTMLElement>('.el-input-number')
      expect(number, `参数「${label}」缺少 el-input-number`).toBeTruthy()
      expect(number!.style.width).toBe('100%')
    },
  )
})
