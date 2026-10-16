/**
 * T285 PromptEditorDialog（红→绿）：加载渲染/状态徽标/长度计数/变量插入/
 * 保存预检警告确认（取消与继续两路径）/空值阻断/恢复默认/脏关闭确认。
 * 契约：006 contracts/prompt-customization-contract.md §2/§3/§4/§7/§8。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'

import { i18n } from '../src/i18n'

vi.mock('../src/api/prompts', () => ({
  getPromptList: vi.fn(),
  getPrompt: vi.fn(),
  savePrompt: vi.fn(),
  resetPrompt: vi.fn(),
  assistPrompt: vi.fn(),
}))

import { getPrompt, resetPrompt, savePrompt } from '../src/api/prompts'
import type { PromptTemplateDetail } from '../src/api/types'
import PromptEditorDialog from '../src/components/common/PromptEditorDialog.vue'

const getPromptMock = vi.mocked(getPrompt)
const savePromptMock = vi.mocked(savePrompt)
const resetPromptMock = vi.mocked(resetPrompt)

const DEFAULT =
  '你是助手。\n{description}\n{existing_nodes}\n{output_contract}\n要求：约 {count} 条。'
const CONTRACT = '输出 JSON，结构：{node_type: ...}'

function detail(overrides: Partial<PromptTemplateDetail> = {}): PromptTemplateDetail {
  return {
    feature: 'seed_expand',
    label: 'AI 扩充（种子扩充）',
    content: DEFAULT,
    default_content: DEFAULT,
    customized: false,
    updated_at: null,
    max_length: 8000,
    variables: [
      { name: 'description', label: '业务描述', render: '有值 →「业务描述：…」' },
      { name: 'existing_nodes', label: '已有节点名单', render: '逐行「已有X：…」' },
      { name: 'count', label: '候选数量', render: '纯数字' },
    ],
    reserved_variables: [
      { name: 'output_contract', label: '输出结构槽位', render: '替换为固定段原文' },
    ],
    output_contract: CONTRACT,
    ...overrides,
  }
}

type Exposed = { open: (feature: string) => void; visible: boolean }

async function mountAndOpen(d: PromptTemplateDetail): Promise<VueWrapper> {
  getPromptMock.mockResolvedValue(d)
  const wrapper = mount(PromptEditorDialog, {
    global: { plugins: [ElementPlus, i18n] },
    attachTo: document.body,
  })
  ;(wrapper.vm as unknown as Exposed).open('seed_expand')
  await flushPromises()
  return wrapper
}

/** Element Plus 的 el-input 会把透传属性挂到内部 textarea 上（inheritAttrs: false） */
function textarea(): HTMLTextAreaElement {
  return document.body.querySelector(
    'textarea[data-test="prompt-textarea"]',
  ) as HTMLTextAreaElement
}

function btn(name: string): HTMLElement {
  return document.body.querySelector(`[data-test="${name}"]`) as HTMLElement
}

async function click(name: string) {
  // MouseEvent：el-button 的 click 事件校验要求鼠标事件（普通 Event 会触发 Vue 告警）
  btn(name).dispatchEvent(new MouseEvent('click', { bubbles: true }))
  await flushPromises()
}

async function setTextarea(wrapper: VueWrapper, value: string) {
  await wrapper.find('textarea[data-test="prompt-textarea"]').setValue(value)
}

beforeEach(() => {
  vi.clearAllMocks()
  document.body.innerHTML = ''
})

describe('PromptEditorDialog 加载与呈现', () => {
  it('加载渲染：标题/默认徽标/模板全文/长度计数/固定段只读块/变量面板', async () => {
    await mountAndOpen(detail())
    expect(getPromptMock).toHaveBeenCalledWith('seed_expand')
    expect(document.body.textContent).toContain('AI 扩充（种子扩充）')
    expect(btn('prompt-status').textContent).toContain('默认')
    expect(textarea().value).toBe(DEFAULT)
    expect(btn('prompt-counter').textContent).toContain(`${DEFAULT.length} / 8000`)
    expect(btn('prompt-contract').textContent).toBe(CONTRACT)
    expect(btn('prompt-var-count')).toBeTruthy()
    expect(btn('prompt-var-output_contract')).toBeTruthy()
  })

  it('已自定义状态呈现', async () => {
    await mountAndOpen(detail({ customized: true, updated_at: '2026-10-16T00:00:00' }))
    expect(btn('prompt-status').textContent).toContain('已自定义')
  })

  it('变量按钮插入 token 至光标处', async () => {
    const wrapper = await mountAndOpen(detail())
    await setTextarea(wrapper, '你好 ')
    const ta = textarea()
    ta.setSelectionRange(3, 3)
    await click('prompt-var-count')
    expect(textarea().value).toBe('你好 {count}')
  })
})

describe('PromptEditorDialog 保存', () => {
  it('clean 模板直接保存并回显已自定义', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    savePromptMock.mockResolvedValue(detail({ customized: true, warnings: [] }))
    const wrapper = await mountAndOpen(detail())
    await setTextarea(wrapper, DEFAULT)
    await click('prompt-save')
    expect(confirmSpy).not.toHaveBeenCalled()
    expect(savePromptMock).toHaveBeenCalledWith('seed_expand', DEFAULT)
    expect(btn('prompt-status').textContent).toContain('已自定义')
  })

  it('警告先确认：取消不保存，确认后保存并呈现服务端警告', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue(new Error('cancel'))
    const wrapper = await mountAndOpen(detail())
    await setTextarea(wrapper, '只有一句指令')
    await click('prompt-save')
    expect(confirmSpy).toHaveBeenCalled()
    expect(savePromptMock).not.toHaveBeenCalled()

    confirmSpy.mockResolvedValue('confirm' as never)
    savePromptMock.mockResolvedValue(
      detail({ customized: true, warnings: [{ code: 'missing_output_contract', message: 'x' }] }),
    )
    await click('prompt-save')
    expect(savePromptMock).toHaveBeenCalledWith('seed_expand', '只有一句指令')
  })

  it('空模板阻断（不发请求）', async () => {
    const wrapper = await mountAndOpen(detail())
    await setTextarea(wrapper, '   ')
    await click('prompt-save')
    expect(savePromptMock).not.toHaveBeenCalled()
  })

  it('保存失败（服务端 400）：保留编辑内容并复位在途状态', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    savePromptMock.mockRejectedValue(new Error('bad_request'))
    const wrapper = await mountAndOpen(detail())
    await setTextarea(wrapper, '只有一句指令')
    await click('prompt-save')
    expect(savePromptMock).toHaveBeenCalled()
    expect(textarea().value).toBe('只有一句指令') // 内容不丢
    expect(btn('prompt-status').textContent).toContain('默认') // 状态未变
    expect(btn('prompt-save').classList.contains('is-loading')).toBe(false) // 在途已复位
  })
})

describe('PromptEditorDialog 恢复默认与关闭', () => {
  it('恢复默认：确认后调用并回显默认全文与默认徽标', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    resetPromptMock.mockResolvedValue(detail())
    await mountAndOpen(detail({ customized: true, content: '自定义 {description} {existing_nodes} {count} {output_contract}' }))
    expect(btn('prompt-status').textContent).toContain('已自定义')
    await click('prompt-reset')
    expect(resetPromptMock).toHaveBeenCalledWith('seed_expand')
    expect(textarea().value).toBe(DEFAULT)
    expect(btn('prompt-status').textContent).toContain('默认')
  })

  it('脏关闭：确认放弃才关闭；取消则留在编辑器', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue(new Error('stay'))
    const wrapper = await mountAndOpen(detail())
    await setTextarea(wrapper, '改动过')
    await click('prompt-close')
    expect(confirmSpy).toHaveBeenCalled()
    expect((wrapper.vm as unknown as Exposed).visible).toBe(true)

    confirmSpy.mockResolvedValue('confirm' as never)
    await click('prompt-close')
    expect((wrapper.vm as unknown as Exposed).visible).toBe(false)
  })

  it('未修改关闭不弹确认', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    const wrapper = await mountAndOpen(detail())
    await click('prompt-close')
    expect(confirmSpy).not.toHaveBeenCalled()
    expect((wrapper.vm as unknown as Exposed).visible).toBe(false)
  })
})
