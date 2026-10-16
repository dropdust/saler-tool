/**
 * AI 提示词接口薄封装（006 契约 §1~§5）。
 * 模板编辑器、两个对话框徽标与 AI 辅助均经此处（类型见 api/types.ts）。
 */
import { api } from './client'
import type {
  PromptAssistResponse,
  PromptFeatureKey,
  PromptTemplateDetail,
  PromptTemplateSummary,
} from './types'

export function getPromptList() {
  return api.get<{ items: PromptTemplateSummary[] }>('/ai/prompts')
}

export function getPrompt(feature: PromptFeatureKey) {
  return api.get<PromptTemplateDetail>(`/ai/prompts/${feature}`)
}

export function savePrompt(feature: PromptFeatureKey, content: string) {
  return api.put<PromptTemplateDetail>(`/ai/prompts/${feature}`, { content })
}

export function resetPrompt(feature: PromptFeatureKey) {
  return api.post<PromptTemplateDetail>(`/ai/prompts/${feature}/reset`)
}

export type PromptAssistPayload =
  | { mode: 'generate'; intent: string }
  | { mode: 'polish'; draft: string }

export function assistPrompt(feature: PromptFeatureKey, payload: PromptAssistPayload) {
  return api.post<PromptAssistResponse>(`/ai/prompts/${feature}/assist`, payload)
}
