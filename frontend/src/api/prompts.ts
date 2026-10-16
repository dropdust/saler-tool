/**
 * AI 提示词接口薄封装（006 契约 §1~§5，模板库版）。
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

export function createTemplate(
  feature: PromptFeatureKey,
  payload: { name: string; content: string; activate?: boolean },
) {
  return api.post<PromptTemplateDetail>(`/ai/prompts/${feature}/templates`, payload)
}

export function updateTemplate(
  feature: PromptFeatureKey,
  templateId: string,
  payload: { name?: string; content?: string },
) {
  return api.put<PromptTemplateDetail>(`/ai/prompts/${feature}/templates/${templateId}`, payload)
}

export function deleteTemplate(feature: PromptFeatureKey, templateId: string) {
  return api.del<PromptTemplateDetail>(`/ai/prompts/${feature}/templates/${templateId}`)
}

export function activateTemplate(feature: PromptFeatureKey, id: string | null) {
  return api.put<PromptTemplateDetail>(`/ai/prompts/${feature}/active`, { id })
}

export type PromptAssistPayload =
  | { mode: 'generate'; intent: string }
  | { mode: 'polish'; draft: string }

export function assistPrompt(feature: PromptFeatureKey, payload: PromptAssistPayload) {
  return api.post<PromptAssistResponse>(`/ai/prompts/${feature}/assist`, payload)
}
