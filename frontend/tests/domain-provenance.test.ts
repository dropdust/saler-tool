/**
 * 域名检索溯源测试：命中计数列 + 溯源弹窗（query 词/任务/首次命中时间）。
 * 背景：异常域名（如酒店预订站）需查明来自哪条 query、哪次任务——归因数据在 domain_seed_hit。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import { i18n } from '../src/i18n'

vi.mock('../src/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
  ApiError: class ApiError extends Error {},
}))

import { api } from '../src/api/client'
import DomainList from '../src/views/leads/DomainList.vue'
import { provenanceRows, provenanceSummary } from '../src/views/leads/domainProvenance'
import type { DomainDetail, DomainRow, DomainSeedHit } from '../src/api/types'

const get = vi.mocked(api.get)

function domainRow(overrides: Partial<DomainRow> = {}): DomainRow {
  return {
    id: 1,
    domain: 'booking.example',
    homepage_url: 'https://booking.example/',
    title: '10 best summer vacation destinations',
    snippet: null,
    source: 'search',
    status: 'pending',
    attempts: 0,
    last_error: null,
    fetched_pages: 0,
    country: null,
    country_source: null,
    language: null,
    language_source: null,
    is_excluded: false,
    exclusion_reason: null,
    company_id: null,
    seed_hits_count: 2,
    last_crawled_at: null,
    created_at: '2026-10-14T03:38:15',
    ...overrides,
  }
}

const HITS: DomainSeedHit[] = [
  {
    seed_id: 584,
    query: '"hex nuts" distributor OR importer qatar',
    lang: 'en',
    source: 'import',
    job_id: 5,
    first_seen_at: '2026-10-14T03:38:15.988470',
  },
  {
    seed_id: 778,
    query: '"sleeve anchors" distributor OR importer south africa',
    lang: 'en',
    source: 'import',
    job_id: 5,
    first_seen_at: '2026-10-14T03:39:07.344103',
  },
]

describe('domainProvenance（纯函数）', () => {
  it('摘要：无命中说明导入来源，有命中给出条数与多 query 提示', () => {
    expect(provenanceSummary([])).toContain('无检索命中记录')
    expect(provenanceSummary(HITS)).toBe('共 2 条检索词命中（同一域名可被多条 query 命中，逐条给出）')
  })

  it('行组装：query 原样、任务标注、时间截断到秒', () => {
    const rows = provenanceRows(HITS)
    expect(rows[0].query).toBe('"hex nuts" distributor OR importer qatar')
    expect(rows[0].jobLabel).toBe('任务 #5')
    expect(rows[0].timeLabel).toBe('2026-10-14 03:38:15')
    expect(provenanceRows([{ ...HITS[0], job_id: null, first_seen_at: null }])[0]).toEqual({
      query: HITS[0].query,
      jobLabel: '—',
      timeLabel: '—',
    })
  })
})

describe('DomainList 溯源弹窗', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    get.mockReset()
  })

  it('命中计数列渲染，点击后请求详情并列出 query 词/任务', async () => {
    get.mockImplementation((path: string) => {
      if (path === '/domains') {
        return Promise.resolve({ items: [domainRow()], total: 1, page: 1, page_size: 50 })
      }
      if (path === '/domains/1') {
        return Promise.resolve({ ...domainRow(), seed_hits: HITS } satisfies DomainDetail)
      }
      return Promise.reject(new Error(`unexpected path ${path}`))
    })
    const wrapper = mount(DomainList, {
      attachTo: document.body,
      global: { plugins: [ElementPlus, i18n] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('2 条')
    await wrapper.find('.provenance-link').trigger('click')
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/domains/1')
    expect(document.body.textContent).toContain('检索溯源：booking.example')
    expect(document.body.textContent).toContain('"hex nuts" distributor OR importer qatar')
    expect(document.body.textContent).toContain('任务 #5')
    expect(document.body.textContent).toContain('2026-10-14 03:38:15')
  })

  it('无命中域名显示占位符且不渲染溯源按钮', async () => {
    get.mockResolvedValue({
      items: [domainRow({ id: 2, domain: 'imported.example', source: 'import', seed_hits_count: null })],
      total: 1,
      page: 1,
      page_size: 50,
    })
    const wrapper = mount(DomainList, {
      attachTo: document.body,
      global: { plugins: [ElementPlus, i18n] },
    })
    await flushPromises()
    expect(wrapper.find('.provenance-link').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('条')
  })
})
