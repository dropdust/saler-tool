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
    note: '注册赠 2,500 次（一次性）',
    apply_url: 'https://serper.dev/dashboard',
    access_mode: 'official_api',
    market: '全球（Google SERP 转售）',
    risk: '预付按量计费；存储/再分发限制见其条款',
  },
  bing_html: {
    display: 'Bing（网页解析）',
    endpoint: 'https://www.bing.com/search',
    needs_key: false,
    note: '免密钥；RSS 形态优先',
    apply_url: null,
    access_mode: 'html',
    market: '全球（免费渠道首选）',
    risk: '非官方接入：受风控影响（静默验证页/地理重定向）',
  },
  ddg_html: {
    display: 'DuckDuckGo（非官方兜底）',
    endpoint: 'https://html.duckduckgo.com/html/',
    needs_key: false,
    note: '非官方端点',
    apply_url: null,
    access_mode: 'html',
    market: '隐私场景 / 最后兜底',
    risk: '软封禁常见（202/403/蜜罐页）',
  },
}

function providerRow(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    type_key: 'serper',
    name: '主 Serper',
    endpoint: null,
    priority: 100,
    enabled: true,
    params: {},
    used_today: 0,
    health: 'unknown',
    last_test_at: null,
    last_test_result: null,
    ...over,
  }
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

describe('检索渠道 · 信息卡（T218 / FR-013~016）', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
    stubApi()
  })

  it('需密钥类型：申请地址链接（新窗口）与决策要点一屏呈现', async () => {
    const wrapper = await openAddDialog()
    const link = wrapper.findAll('a').find((a) => a.text().includes('serper.dev'))
    expect(link).toBeTruthy()
    expect(link!.attributes('href')).toBe('https://serper.dev/dashboard')
    expect(link!.attributes('target')).toBe('_blank') // 系统浏览器打开（既有外链模式）
    const text = document.body.textContent ?? ''
    expect(text).toContain('官方 API') // 接入方式标签
    expect(text).toContain('全球（Google SERP 转售）') // market
    expect(text).toContain('注册赠 2,500 次（一次性）') // note（额度要点）
    expect(text).toContain('预付按量计费') // risk（条款风险）
  })

  it('免密钥类型：网页解析标签 + 风险提示可见，无"申请密钥"行', async () => {
    const wrapper = await openAddDialog()
    await switchType(wrapper, 'bing_html')
    const text = document.body.textContent ?? ''
    expect(text).toContain('网页解析')
    expect(text).toContain('非官方接入：受风控影响') // FR-020 风险提示
    expect(text).not.toContain('前往官方申请页')
  })

  it('编辑既有渠道同样可见信息卡（FR-015）', async () => {
    mockedApi.get.mockImplementation(async (path: string) => {
      if (path === '/search/providers') return [providerRow()]
      if (path === '/search/presets') return { presets: PRESETS, config_schemas: {} }
      return {}
    })
    const wrapper = mount(SearchProviders, {
      global: { plugins: [ElementPlus] },
      attachTo: document.body,
    })
    await flushPromises()
    const editBtn = wrapper.findAll('button').find((b) => b.text().includes('编辑'))
    expect(editBtn).toBeTruthy()
    await editBtn!.trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('前往官方申请页')
  })
})
