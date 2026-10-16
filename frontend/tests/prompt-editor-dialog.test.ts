/**
 * T299 PromptEditorDialog（模板库版，红→绿）：选择器（选择即生效）/另存为/重命名/删除（生效回退）/
 * 保存（具名=更新；默认态=引导另存为）/预检警告确认/恢复默认（保留库）/脏状态确认。
 * 契约：006 contracts/prompt-customization-contract.md §2~§4/§7/§8（模板库版）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElMessage, ElMessageBox, ElSelect } from 'element-plus'

import { i18n } from '../src/i18n'

vi.mock('../src/api/prompts', () => ({
  getPromptList: vi.fn(),
  getPrompt: vi.fn(),
  createTemplate: vi.fn(),
  updateTemplate: vi.fn(),
  deleteTemplate: vi.fn(),
  activateTemplate: vi.fn(),
  assistPrompt: vi.fn(),
}))

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
  sseUrl: (path: string) => path,
}))

import {
  activateTemplate,
  assistPrompt,
  createTemplate,
  deleteTemplate,
  getPrompt,
  updateTemplate,
} from '../src/api/prompts'
import { api } from '../src/api/client'
import type { PromptTemplateDetail, PromptTemplateItem } from '../src/api/types'
import PromptEditorDialog from '../src/components/common/PromptEditorDialog.vue'

const getPromptMock = vi.mocked(getPrompt)
const createMock = vi.mocked(createTemplate)
const updateMock = vi.mocked(updateTemplate)
const deleteMock = vi.mocked(deleteTemplate)
const activateMock = vi.mocked(activateTemplate)
const assistMock = vi.mocked(assistPrompt)
const clientGetMock = vi.mocked(api.get)

const DEFAULT =
  '你是助手。\n{description}\n{existing_nodes}\n{output_contract}\n要求：约 {count} 条。'
const CONTRACT = '输出 JSON，结构：{node_type: ...}'
const TEMPLATE_A = 'A 指令 {description} {existing_nodes} {count} {output_contract}'
const TEMPLATE_B = 'B 指令 {description} {existing_nodes} {count} {output_contract}'

function item(id: string, name: string, content: string): PromptTemplateItem {
  return { id, name, content, updated_at: '2026-10-16T00:00:00' }
}

function detail(overrides: Partial<PromptTemplateDetail> = {}): PromptTemplateDetail {
  return {
    feature: 'seed_expand',
    label: 'AI 扩充（种子扩充）',
    default_content: DEFAULT,
    active_id: null,
    active_name: null,
    customized: false,
    max_length: 8000,
    max_name_length: 60,
    max_templates: 50,
    templates: [],
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

const ACTIVE_A = detail({
  active_id: 't_a',
  active_name: '东非市场',
  customized: true,
  templates: [item('t_a', '东非市场', TEMPLATE_A), item('t_b', '展会渠道', TEMPLATE_B)],
})

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

function textarea(): HTMLTextAreaElement {
  return document.body.querySelector(
    'textarea[data-test="prompt-textarea"]',
  ) as HTMLTextAreaElement
}

function btn(name: string): HTMLElement {
  return document.body.querySelector(`[data-test="${name}"]`) as HTMLElement
}

async function click(name: string) {
  btn(name).dispatchEvent(new MouseEvent('click', { bubbles: true }))
  await flushPromises()
}

async function setTextarea(wrapper: VueWrapper, value: string) {
  await wrapper.find('textarea[data-test="prompt-textarea"]').setValue(value)
}

/** 通过 ElSelect 组件事件驱动选择器（jsdom 不便展开下拉） */
async function selectTemplate(wrapper: VueWrapper, id: string) {
  wrapper.findComponent(ElSelect).vm.$emit('change', id)
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
  document.body.innerHTML = ''
})

describe('PromptEditorDialog 加载与呈现', () => {
  it('默认态：选择器=内置默认、模板全文/计数/固定段/变量面板、状态「默认」', async () => {
    const wrapper = await mountAndOpen(detail())
    expect(getPromptMock).toHaveBeenCalledWith('seed_expand')
    // 下拉未展开时仅选中项渲染标签
    expect(document.body.textContent).toContain('内置默认')
    // 默认态选择器值为 ''（el-select 视为「未选择」，不渲染选中标签）——「当前=内置默认」由
    // placeholder 承担（T301 真实浏览器验收发现：缺失时实际显示灰色「请选择」，与 quickstart V1② 不符）
    expect(wrapper.findComponent(ElSelect).props('placeholder')).toBe('内置默认（不可修改）')
    expect(btn('prompt-status').textContent).toContain('默认')
    expect(textarea().value).toBe(DEFAULT)
    expect(btn('prompt-counter').textContent).toContain(`${DEFAULT.length} / 8000`)
    expect(btn('prompt-contract').textContent).toBe(CONTRACT)
    expect(btn('prompt-var-count')).toBeTruthy()
  })

  it('具名生效态：选择器/状态显示模板名、文本域载入其内容、重命名/删除可用', async () => {
    await mountAndOpen(ACTIVE_A)
    expect(btn('prompt-status').textContent).toContain('东非市场')
    expect(textarea().value).toBe(TEMPLATE_A)
    expect((btn('prompt-rename') as HTMLButtonElement).disabled).toBe(false)
    expect((btn('prompt-delete') as HTMLButtonElement).disabled).toBe(false)
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

describe('PromptEditorDialog 选择与切换（选择即生效）', () => {
  it('切换到具名模板：调 activate 并载入全文', async () => {
    activateMock.mockResolvedValue({
      ...ACTIVE_A,
      active_id: 't_b',
      active_name: '展会渠道',
    })
    const wrapper = await mountAndOpen(detail({ templates: [item('t_b', '展会渠道', TEMPLATE_B)] }))
    await selectTemplate(wrapper, 't_b')
    expect(activateMock).toHaveBeenCalledWith('seed_expand', 't_b')
    expect(textarea().value).toBe(TEMPLATE_B)
    expect(btn('prompt-status').textContent).toContain('展会渠道')
  })

  it('切回内置默认：activate null', async () => {
    activateMock.mockResolvedValue(detail({ templates: ACTIVE_A.templates }))
    const wrapper = await mountAndOpen(ACTIVE_A)
    await selectTemplate(wrapper, '')
    expect(activateMock).toHaveBeenCalledWith('seed_expand', null)
    expect(textarea().value).toBe(DEFAULT)
  })

  it('脏状态切走：确认放弃才切换；取消不切换', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue(new Error('stay'))
    const wrapper = await mountAndOpen(ACTIVE_A)
    await setTextarea(wrapper, '改动过')
    await selectTemplate(wrapper, 't_b')
    expect(confirmSpy).toHaveBeenCalled()
    expect(activateMock).not.toHaveBeenCalled()

    confirmSpy.mockResolvedValue('confirm' as never)
    activateMock.mockResolvedValue({ ...ACTIVE_A, active_id: 't_b', active_name: '展会渠道' })
    await selectTemplate(wrapper, 't_b')
    expect(activateMock).toHaveBeenCalledWith('seed_expand', 't_b')
  })
})

describe('PromptEditorDialog 保存（具名=更新；默认态=另存为引导，FR-015）', () => {
  it('具名生效：更新内容，clean 直接调用', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    updateMock.mockResolvedValue({ ...ACTIVE_A, warnings: [] })
    const wrapper = await mountAndOpen(ACTIVE_A)
    await setTextarea(wrapper, TEMPLATE_A + '\n新增要求')
    await click('prompt-save')
    expect(confirmSpy).not.toHaveBeenCalled()
    expect(updateMock).toHaveBeenCalledWith('seed_expand', 't_a', { content: TEMPLATE_A + '\n新增要求' })
  })

  it('具名生效：警告先确认——取消不保存，确认后保存', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue(new Error('cancel'))
    const wrapper = await mountAndOpen(ACTIVE_A)
    await setTextarea(wrapper, '只有一句指令')
    await click('prompt-save')
    expect(confirmSpy).toHaveBeenCalled()
    expect(updateMock).not.toHaveBeenCalled()

    confirmSpy.mockResolvedValue('confirm' as never)
    updateMock.mockResolvedValue({ ...ACTIVE_A, warnings: [{ code: 'missing_output_contract', message: 'x' }] })
    await click('prompt-save')
    expect(updateMock).toHaveBeenCalledWith('seed_expand', 't_a', { content: '只有一句指令' })
  })

  it('默认态保存：引导另存为（命名后创建即生效）', async () => {
    const promptSpy = vi
      .spyOn(ElMessageBox, 'prompt')
      .mockResolvedValue({ value: '新模板', action: 'confirm' } as never)
    createMock.mockResolvedValue({
      ...detail(),
      active_id: 't_new',
      active_name: '新模板',
      customized: true,
      templates: [item('t_new', '新模板', DEFAULT)],
    })
    const wrapper = await mountAndOpen(detail())
    await setTextarea(wrapper, DEFAULT)
    await click('prompt-save')
    expect(promptSpy).toHaveBeenCalled()
    expect(createMock).toHaveBeenCalledWith('seed_expand', {
      name: '新模板',
      content: DEFAULT,
      activate: true,
    })
    expect(btn('prompt-status').textContent).toContain('新模板')
  })

  it('默认态保存：另存为取消则不落库、编辑内容保留', async () => {
    vi.spyOn(ElMessageBox, 'prompt').mockRejectedValue(new Error('cancel'))
    const wrapper = await mountAndOpen(detail())
    await setTextarea(wrapper, '编辑中的内容')
    await click('prompt-save')
    expect(createMock).not.toHaveBeenCalled()
    expect(textarea().value).toBe('编辑中的内容')
  })

  it('空模板阻断（不发请求）', async () => {
    const wrapper = await mountAndOpen(ACTIVE_A)
    await setTextarea(wrapper, '   ')
    await click('prompt-save')
    expect(updateMock).not.toHaveBeenCalled()
    expect(createMock).not.toHaveBeenCalled()
  })

  it('超长阻断（T296 边界）：计数器变红、不发请求（额度提示）', async () => {
    const wrapper = await mountAndOpen(ACTIVE_A)
    await setTextarea(wrapper, 'x'.repeat(8001))
    expect(btn('prompt-counter').classList.contains('over')).toBe(true)
    await click('prompt-save')
    expect(updateMock).not.toHaveBeenCalled()
    expect(createMock).not.toHaveBeenCalled() // 也走不到「另存为」引导
  })

  it('保存失败（服务端 400）：保留编辑内容并复位在途状态', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    updateMock.mockRejectedValue(new Error('bad_request'))
    const wrapper = await mountAndOpen(ACTIVE_A)
    await setTextarea(wrapper, '只有一句指令')
    await click('prompt-save')
    expect(updateMock).toHaveBeenCalled()
    expect(textarea().value).toBe('只有一句指令')
    expect(btn('prompt-save').classList.contains('is-loading')).toBe(false)
  })
})

describe('PromptEditorDialog 另存为/重命名/删除/恢复默认', () => {
  it('另存为：命名后创建（activate=true）', async () => {
    vi.spyOn(ElMessageBox, 'prompt').mockResolvedValue({ value: '展会渠道', action: 'confirm' } as never)
    createMock.mockResolvedValue({ ...ACTIVE_A, active_id: 't_new', active_name: '展会渠道' })
    const wrapper = await mountAndOpen(ACTIVE_A)
    await setTextarea(wrapper, TEMPLATE_A + '\n展会版')
    await click('prompt-save-as')
    expect(createMock).toHaveBeenCalledWith('seed_expand', {
      name: '展会渠道',
      content: TEMPLATE_A + '\n展会版',
      activate: true,
    })
  })

  it('重命名：prompt 命名后调 update；取消不调用', async () => {
    const promptSpy = vi.spyOn(ElMessageBox, 'prompt').mockRejectedValue(new Error('cancel'))
    await mountAndOpen(ACTIVE_A)
    await click('prompt-rename')
    expect(promptSpy).toHaveBeenCalled()
    expect(updateMock).not.toHaveBeenCalled()

    promptSpy.mockResolvedValue({ value: '东非-电力', action: 'confirm' } as never)
    updateMock.mockResolvedValue({ ...ACTIVE_A, active_name: '东非-电力' })
    await click('prompt-rename')
    expect(updateMock).toHaveBeenCalledWith('seed_expand', 't_a', { name: '东非-电力' })
    expect(btn('prompt-status').textContent).toContain('东非-电力')
  })

  it('删除生效模板：确认后调 delete，服务端回退默认并刷新呈现', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    deleteMock.mockResolvedValue(detail({ templates: [item('t_b', '展会渠道', TEMPLATE_B)] }))
    await mountAndOpen(ACTIVE_A)
    await click('prompt-delete')
    expect(deleteMock).toHaveBeenCalledWith('seed_expand', 't_a')
    expect(btn('prompt-status').textContent).toContain('默认')
    expect(textarea().value).toBe(DEFAULT)
  })

  it('默认态下重命名/删除置灰', async () => {
    await mountAndOpen(detail({ templates: [item('t_b', '展会渠道', TEMPLATE_B)] }))
    expect((btn('prompt-rename') as HTMLButtonElement).disabled).toBe(true)
    expect((btn('prompt-delete') as HTMLButtonElement).disabled).toBe(true)
  })

  it('恢复默认：确认后 activate null（模板库保留）', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    activateMock.mockResolvedValue(detail({ templates: ACTIVE_A.templates }))
    await mountAndOpen(ACTIVE_A)
    await click('prompt-restore-default')
    expect(activateMock).toHaveBeenCalledWith('seed_expand', null)
    expect(textarea().value).toBe(DEFAULT)
    expect(btn('prompt-status').textContent).toContain('默认')
  })

  it('恢复默认：默认态下置灰', async () => {
    await mountAndOpen(detail())
    expect((btn('prompt-restore-default') as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('PromptEditorDialog 关闭', () => {
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

describe('PromptEditorDialog AI 辅助（T292，006 §5 / FR-009~012）', () => {
  it('AI 生成：空意图不请求；有意图按参数调用并渲染建议；编辑器内容未变', async () => {
    const wrapper = await mountAndOpen(detail())
    assistMock.mockResolvedValue({ suggestion: '建议模板 {description} {output_contract}', notes: '保留变量' })

    await click('assist-generate') // 空意图
    expect(assistMock).not.toHaveBeenCalled()

    await wrapper.find('input[data-test="assist-intent"]').setValue('面向东非市场')
    await click('assist-generate')
    expect(assistMock).toHaveBeenCalledWith('seed_expand', {
      mode: 'generate',
      intent: '面向东非市场',
    })
    expect(btn('assist-suggestion').textContent).toContain('建议模板')
    expect(btn('assist-notes').textContent).toContain('保留变量')
    expect(textarea().value).toBe(DEFAULT) // 建议态不自动写入
  })

  it('AI 优化当前草稿：携带编辑器当前文本；请求期间编辑器可继续编辑', async () => {
    const wrapper = await mountAndOpen(detail())
    await setTextarea(wrapper, '我的草稿 {description}')
    assistMock.mockImplementation(() => new Promise(() => {}) as never) // 挂起以观察在途态

    await click('assist-polish')
    expect(assistMock).toHaveBeenCalledWith('seed_expand', {
      mode: 'polish',
      draft: '我的草稿 {description}',
    })
    expect(btn('assist-polish').classList.contains('is-loading')).toBe(true)
    await setTextarea(wrapper, '继续编辑中')
    expect(textarea().value).toBe('继续编辑中')
  })

  it('采用：建议写入编辑器（dirty）但不保存；关闭重开回到已保存内容', async () => {
    const wrapper = await mountAndOpen(detail())
    assistMock.mockResolvedValue({
      suggestion: '采用后模板 {description} {existing_nodes} {count} {output_contract}',
      notes: null,
    })
    await wrapper.find('input[data-test="assist-intent"]').setValue('x')
    await click('assist-generate')
    await click('assist-adopt')

    expect(textarea().value).toBe('采用后模板 {description} {existing_nodes} {count} {output_contract}')
    expect(createMock).not.toHaveBeenCalled()
    expect(updateMock).not.toHaveBeenCalled()
    expect(activateMock).not.toHaveBeenCalled()

    // 采用≠保存：脏关闭确认放弃后重开，已保存内容（内置默认）不变
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    await click('prompt-close')
    ;(wrapper.vm as unknown as Exposed).open('seed_expand')
    await flushPromises()
    expect(textarea().value).toBe(DEFAULT)
  })

  it('丢弃：建议区消失、编辑器原文不变', async () => {
    const wrapper = await mountAndOpen(detail())
    assistMock.mockResolvedValue({ suggestion: 'S', notes: null })
    await wrapper.find('input[data-test="assist-intent"]').setValue('x')
    await click('assist-generate')
    expect(btn('assist-suggestion')).toBeTruthy()

    await click('assist-discard')
    expect(document.body.querySelector('[data-test="assist-suggestion"]')).toBeNull()
    expect(textarea().value).toBe(DEFAULT)
  })

  it('辅助失败：建议区不出现、编辑器内容无损、在途复位', async () => {
    const wrapper = await mountAndOpen(detail())
    await setTextarea(wrapper, '我的草稿')
    assistMock.mockRejectedValue(new Error('boom'))
    await click('assist-polish')
    expect(document.body.querySelector('[data-test="assist-suggestion"]')).toBeNull()
    expect(textarea().value).toBe('我的草稿')
    expect(btn('assist-polish').classList.contains('is-loading')).toBe(false)
  })

  it('409 未配置：给出「设置 → 大模型」指引且内容无损', async () => {
    const warningSpy = vi.spyOn(ElMessage, 'warning')
    const wrapper = await mountAndOpen(detail())
    await setTextarea(wrapper, '我的草稿')
    assistMock.mockRejectedValue(
      Object.assign(new Error('无服务'), { code: 'llm_not_configured' }),
    )
    await click('assist-polish')
    expect(
      warningSpy.mock.calls.some((call) => String(call[0]).includes('设置')),
    ).toBe(true)
    expect(textarea().value).toBe('我的草稿')
  })

  it('查看调用明细：以 operation=prompt_assist 打开抽屉', async () => {
    clientGetMock.mockResolvedValue({ total: 0, items: [] })
    const wrapper = await mountAndOpen(detail())
    assistMock.mockResolvedValue({ suggestion: 'S', notes: null })
    await wrapper.find('input[data-test="assist-intent"]').setValue('x')
    await click('assist-generate')

    await click('assist-view-calls')
    expect(clientGetMock).toHaveBeenCalledWith('/ai/calls', {
      operation: 'prompt_assist',
      limit: 20,
      offset: 0,
    })
    expect(document.body.textContent).toContain('AI 调用明细')
  })
})
