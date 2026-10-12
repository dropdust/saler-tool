/**
 * T212 组件测试（004-search-channel-expansion，红阶段）：检索渠道页——密钥字段按
 * `presets[type_key].needs_key` 数据驱动（FR-002：免密钥渠道 MUST NOT 要求密钥字段）。
 * 用例以 needs_key=false 的非 ddg 类型（bing_html）区分"硬编码特判"与"数据驱动"。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import ElementPlus from 'element-plus'

import { api } from '../src/api/client'
import SearchProviders from '../src/views/settings/SearchProviders.vue'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
}))

const mockedApi = vi.mocked(api)

const PRESETS: Record<string, Record<string, unknown>> = {
  serper: {
    display: 'Serper.dev（Google SERP）',
    endpoint: 'https://google.serper.dev',
    needs_key: true,
    note: '注册赠额度',
  },
  bing_html: {
    display: 'Bing（网页解析）',
    endpoint: 'https://www.bing.com/search',
    needs_key: false,
    note: '免密钥；RSS 形态优先',
  },
  ddg_html: {
    display: 'DuckDuckGo（非官方兜底）',
    endpoint: 'https://html.duckduckgo.com/html/',
    needs_key: false,
    note: '非官方端点',
  },
}

function stubApi() {
  mockedApi.get.mockImplementation(async (path: string) => {
    if (path === '/search/providers') return []
    if (path === '/search/presets') return { presets: PRESETS, config_schemas: {} }
    return {}
  })
  mockedApi.post.mockResolvedValue({})
  mockedApi.put.mockResolvedValue({})
}

async function openAddDialog(): Promise<VueWrapper> {
  const wrapper = mount(SearchProviders, {
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await flushPromises()
  const addBtn = wrapper.findAll('button').find((b) => b.text().includes('添加渠道'))
  expect(addBtn).toBeTruthy()
  await addBtn!.trigger('click')
  await flushPromises()
  return wrapper
}

function passwordInputs(wrapper: VueWrapper) {
  return wrapper
    .findAllComponents({ name: 'ElInput' })
    .filter((i) => i.props('type') === 'password')
}

async function switchType(wrapper: VueWrapper, typeKey: string) {
  const select = wrapper.findComponent({ name: 'ElSelect' })
  select.vm.$emit('update:modelValue', typeKey)
  select.vm.$emit('change')
  await nextTick()
  await flushPromises()
}

describe('检索渠道 · 密钥字段数据驱动（T212 / FR-002）', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
    stubApi()
  })

  it('需密钥类型渲染密钥输入框（默认 serper）', async () => {
    const wrapper = await openAddDialog()
    expect(passwordInputs(wrapper).length).toBe(1)
    expect(document.body.textContent).not.toContain('无需密钥')
  })

  it('切换免密钥类型（bing_html）后隐藏输入框并显示"无需密钥"，提交不含 api_key', async () => {
    const wrapper = await openAddDialog()
    await switchType(wrapper, 'bing_html')

    expect(passwordInputs(wrapper).length).toBe(0)
    expect(document.body.textContent).toContain('无需密钥')

    const saveBtn = wrapper.findAll('button').find((b) => b.text().includes('保存'))
    expect(saveBtn).toBeTruthy()
    await saveBtn!.trigger('click')
    await flushPromises()

    expect(mockedApi.post).toHaveBeenCalledWith(
      '/search/providers',
      expect.objectContaining({ type_key: 'bing_html' }),
    )
    const payload = mockedApi.post.mock.calls[0]![1] as Record<string, unknown>
    expect('api_key' in payload).toBe(false)
  })

  it('再切回需密钥类型恢复输入框', async () => {
    const wrapper = await openAddDialog()
    await switchType(wrapper, 'bing_html')
    await switchType(wrapper, 'serper')
    expect(passwordInputs(wrapper).length).toBe(1)
  })
})
