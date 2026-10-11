/**
 * T180 纯函数单测（003-seed-language-filter，红阶段）：语言筛选选项组装。
 * 对应 FR-001/006：选项 = 统一语言表 LANGS 全量（固定顺序、中文标签）+ 库内非标准精确取值（原样 code）。
 */

import { describe, expect, it } from 'vitest'

import { LANGS, langFilterOptions } from '../src/constants'

describe('langFilterOptions（语言筛选选项组装）', () => {
  it('标准语言全量在列、顺序与统一语言表一致、标签为"中文标签（code）"', () => {
    const options = langFilterOptions([])
    expect(options.map((item) => item.value)).toEqual(LANGS.map((item) => item.code))
    expect(options[0]).toEqual({ value: 'en', label: '英语（en）' })
    expect(options.find((item) => item.value === 'ru')?.label).toBe('俄语（ru）')
  })

  it('库内非标准取值按传入顺序原样追加，标签=原值 code', () => {
    const options = langFilterOptions(['EN', 'ko'])
    expect(options.slice(LANGS.length)).toEqual([
      { value: 'EN', label: 'EN' },
      { value: 'ko', label: 'ko' },
    ])
  })

  it('present 含标准码/重复值时不重复追加', () => {
    const options = langFilterOptions(['ru', 'ru', 'en', 'ko', 'ko'])
    expect(options).toHaveLength(LANGS.length + 1)
    expect(options.filter((item) => item.value === 'ru')).toHaveLength(1)
    expect(options.filter((item) => item.value === 'ko')).toHaveLength(1)
  })

  it('大小写变体与标准码并存——EN 与 en 为两个独立选项（互不混淆）', () => {
    const values = langFilterOptions(['EN']).map((item) => item.value)
    expect(values).toContain('en')
    expect(values).toContain('EN')
    expect(values.filter((value) => value.toLowerCase() === 'en')).toHaveLength(2)
  })
})
