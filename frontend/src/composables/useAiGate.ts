import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'

/**
 * AI 降级门（FR-032 / SC-010）：
 * 未配置大模型服务时，AI 入口给出明确提示；手工与规则功能不受影响。
 * 模块级共享状态：多处视图共用一次探测结果。
 */

const aiReady = ref(false)
const checked = ref(false)

export function useAiGate() {
  async function refresh(): Promise<boolean> {
    try {
      const rows = await api.get<unknown[]>('/llm/providers')
      aiReady.value = rows.length > 0
    } catch {
      aiReady.value = false
    }
    checked.value = true
    return aiReady.value
  }

  async function requireAi(): Promise<boolean> {
    const ready = checked.value ? aiReady.value : await refresh()
    if (!ready) {
      ElMessage.warning('尚未配置大模型服务：请先在「设置 → 大模型服务」中添加并测试')
    }
    return ready
  }

  return { aiReady, refresh, requireAi }
}
