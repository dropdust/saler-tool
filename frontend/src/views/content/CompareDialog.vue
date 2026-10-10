<template>
  <el-dialog v-model="visible" :title="`多语言对照 · ${theme?.name ?? ''}`" width="86%" top="6vh">
    <div v-loading="loading" class="compare-wrap">
      <div v-for="variant in variants" :key="variant.id" class="column">
        <div class="column-head">
          <strong>{{ langLabel(variant.lang) }}</strong>
          <StatusTag :status="variant.status" />
        </div>
        <div class="meta">
          {{ SOURCE_LABELS[variant.source] || variant.source }}
          · v{{ variant.current?.version_no ?? '—' }}
        </div>
        <div v-if="theme?.content_type === 'email'" class="subject">
          <span class="label">主题行：</span>{{ variant.current?.subject || '（空）' }}
        </div>
        <pre class="body">{{ variant.current?.body_md || '（空）' }}</pre>
        <div class="vars">
          <el-tag v-for="name in variant.current?.variables || []" :key="name" size="small" class="chip">
            {{ name }}
          </el-tag>
        </div>
      </div>
      <EmptyState v-if="!loading && !variants.length" description="尚无语言版本" />
    </div>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../../api/client'
import type { ContentThemeRow, ContentVariantRow } from '../../api/types'
import StatusTag from '../../components/common/StatusTag.vue'
import EmptyState from '../../components/common/EmptyState.vue'
import { langLabel } from '../../constants'

const SOURCE_LABELS: Record<string, string> = {
  manual: '手工',
  llm_assisted: 'AI 辅助编写',
  llm_translated: 'AI 翻译',
}

const visible = ref(false)
const loading = ref(false)
const theme = ref<ContentThemeRow | null>(null)
const variants = ref<ContentVariantRow[]>([])

async function open(themeId: number) {
  visible.value = true
  loading.value = true
  try {
    const detail = await api.get<ContentThemeRow>(`/content/themes/${themeId}`)
    theme.value = detail
    variants.value = detail.variants ?? []
  } finally {
    loading.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.compare-wrap {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  min-height: 160px;
}
.column {
  flex: 0 0 340px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
}
.column-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.subject {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}
.subject .label {
  color: var(--el-text-color-secondary);
  font-weight: 400;
}
.body {
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 10px;
  margin: 0 0 8px;
  font-family: inherit;
  font-size: 12.5px;
  line-height: 1.6;
  flex: 1;
  max-height: 52vh;
  overflow: auto;
}
.chip {
  margin-right: 4px;
}
</style>
