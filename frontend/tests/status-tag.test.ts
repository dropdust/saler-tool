/**
 * T194 组件测试（红阶段）：StatusTag 审核域标签（F1 术语修正）。
 * review 域 pending 必须显示"待审核"（与审核筛选下拉口径一致）；执行状态域与其他域语义不变。
 */

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import StatusTag from '../src/components/common/StatusTag.vue'
import { i18n } from '../src/i18n'

function mountTag(props: { status: string; domain?: 'review' }) {
  return mount(StatusTag, { props, global: { plugins: [ElementPlus, i18n] } })
}

describe('StatusTag（审核域标签，F1）', () => {
  it('domain=review + pending → "待审核"（与审核筛选下拉一致）', () => {
    expect(mountTag({ status: 'pending', domain: 'review' }).text()).toBe('待审核')
  })

  it('无 domain（执行状态域）+ pending → "待执行"（语义不变）', () => {
    expect(mountTag({ status: 'pending' }).text()).toBe('待执行')
  })

  it('domain=review 的 approved/rejected 标签保持"已采纳/已拒绝"', () => {
    expect(mountTag({ status: 'approved', domain: 'review' }).text()).toBe('已采纳')
    expect(mountTag({ status: 'rejected', domain: 'review' }).text()).toBe('已拒绝')
  })

  it('未知状态值原样显示（不回归）', () => {
    expect(mountTag({ status: 'weird' }).text()).toBe('weird')
  })
})

// 005 T229：任务中断态（启动对账写入的终态，契约 §2）
describe('StatusTag（任务中断态）', () => {
  it('interrupted → "已中断" 且配色 warning（区别于 failed/cancelled）', () => {
    const wrapper = mountTag({ status: 'interrupted' })
    expect(wrapper.text()).toBe('已中断')
    expect(wrapper.find('.el-tag--warning').exists()).toBe(true)
  })
})
