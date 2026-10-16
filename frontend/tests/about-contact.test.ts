/**
 * T302 关于与联系（红→绿）：设置 →「关于与联系」——QQ 群 / 微信 / GitHub 仓库三条用户渠道
 * 可见、可复制、可跳转；路由与侧栏接线。二维码走 Vite 资源管道（随包分发，缺图即构建失败）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { defineComponent, h } from 'vue'

import { i18n } from '../src/i18n'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
  sseUrl: (path: string) => path,
}))

import { api } from '../src/api/client'
import About from '../src/views/settings/About.vue'
import MainLayout from '../src/layouts/MainLayout.vue'
import router from '../src/router'
import { useAppStore } from '../src/stores/app'
import qqgroupQr from '../src/assets/qqgroup.jpg'
import wechatQr from '../src/assets/wx.png'

const mockedApi = vi.mocked(api)

const REPO_URL = 'https://github.com/dropdust/saler-tool'
const ISSUES_URL = 'https://github.com/dropdust/saler-tool/issues'
const QQ_GROUP_NUMBER = '1128098127'

const writeText = vi.fn()

function mountAbout(version: string | null = '9.9.9-test'): VueWrapper {
  const pinia = createPinia()
  setActivePinia(pinia)
  if (version !== null) {
    useAppStore().health = { ok: true, version }
  }
  return mount(About, { global: { plugins: [pinia, ElementPlus, i18n] } })
}

function imgSrc(wrapper: VueWrapper, selector: string): string {
  const img = wrapper.find(selector)
  expect(img.exists(), `未找到图片 ${selector}`).toBe(true)
  return img.attributes('src') ?? ''
}

beforeEach(() => {
  vi.clearAllMocks()
  writeText.mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
  })
  mockedApi.get.mockImplementation(async (path: string) =>
    path === '/jobs' ? { items: [], total: 0, page: 1, page_size: 100 } : {},
  )
})

describe('About 关于与联系 · 渠道内容', () => {
  it('QQ 群：群名、群号与二维码（alt 带群号，无障碍可达）', () => {
    const wrapper = mountAbout()
    expect(wrapper.text()).toContain('外贸获客工具')
    expect(wrapper.text()).toContain(QQ_GROUP_NUMBER)
    const qr = wrapper.find('[data-test="qq-qr"]')
    expect(qr.exists()).toBe(true)
    expect(qr.attributes('alt')).toContain(QQ_GROUP_NUMBER)
  })

  it('微信：昵称与扫码提示', () => {
    const wrapper = mountAbout()
    expect(wrapper.text()).toContain('码工李葛')
    expect(wrapper.text()).toContain('扫二维码，添加我为朋友')
    expect(wrapper.find('[data-test="wx-qr"]').attributes('alt')).toBeTruthy()
  })

  it('两张二维码取自随包的资源模块（不是凭空写死的路径）', () => {
    const wrapper = mountAbout()
    expect(imgSrc(wrapper, '[data-test="qq-qr"]')).toBe(qqgroupQr)
    expect(imgSrc(wrapper, '[data-test="wx-qr"]')).toBe(wechatQr)
  })
})

describe('About 关于与联系 · 仓库与版本', () => {
  it('GitHub 仓库与 Issues 外链：新开页签，且地址明文可见', () => {
    const wrapper = mountAbout()
    const repo = wrapper.find('[data-test="github-link"]')
    expect(repo.element.tagName).toBe('A')
    expect(repo.attributes('href')).toBe(REPO_URL)
    expect(repo.attributes('target')).toBe('_blank')
    expect(wrapper.text()).toContain(REPO_URL)
    expect(wrapper.find('[data-test="issues-link"]').attributes('href')).toBe(ISSUES_URL)
  })

  it('版本号取自 /health（不硬编码）', () => {
    const wrapper = mountAbout('9.9.9-test')
    expect(wrapper.find('[data-test="app-version"]').text()).toBe('v9.9.9-test')
  })

  it('本地服务信息缺失时版本降级为 —，不崩', () => {
    const wrapper = mountAbout(null)
    expect(wrapper.find('[data-test="app-version"]').text()).toBe('—')
  })
})

describe('About 关于与联系 · 复制', () => {
  it('复制群号写入剪贴板', async () => {
    const wrapper = mountAbout()
    await wrapper.find('[data-test="copy-qq-group"]').trigger('click')
    expect(writeText).toHaveBeenCalledWith(QQ_GROUP_NUMBER)
  })

  it('复制仓库地址写入剪贴板', async () => {
    const wrapper = mountAbout()
    await wrapper.find('[data-test="copy-repo"]').trigger('click')
    expect(writeText).toHaveBeenCalledWith(REPO_URL)
  })

  it('剪贴板不可用时降级为明文提示（既有口径，不静默失败）', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
    const info = vi.spyOn(ElMessage, 'info')
    const wrapper = mountAbout()
    await wrapper.find('[data-test="copy-qq-group"]').trigger('click')
    await flushPromises()
    expect(info).toHaveBeenCalledWith(QQ_GROUP_NUMBER)
  })
})

describe('关于与联系 · 接线', () => {
  it('路由 /settings/about 已注册', () => {
    const route = router.getRoutes().find((item) => item.name === 'settings-about')
    expect(route?.path).toBe('/settings/about')
    expect(route?.meta.title).toBe('关于与联系')
  })

  it('侧栏「设置」子菜单含入口，指向 /settings/about', async () => {
    const pinia = createPinia()
    const stub: Router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: defineComponent({ render: () => h('div') }), meta: { title: '总览' } },
      ],
    })
    await stub.push('/')
    await stub.isReady()
    const wrapper = mount(MainLayout, {
      global: { plugins: [pinia, stub, ElementPlus, i18n] },
      attachTo: document.body,
    })
    await flushPromises()
    const indexes = wrapper
      .findAllComponents({ name: 'ElMenuItem' })
      .map((item) => item.props('index'))
    expect(indexes).toContain('/settings/about')
    expect(wrapper.text()).toContain('关于与联系')
    wrapper.unmount()
  })
})
