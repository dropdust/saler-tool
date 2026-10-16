<template>
  <el-dialog
    v-model="visible"
    :title="`AI 提示词 · ${detail?.label ?? ''}`"
    width="720px"
    :before-close="handleBeforeClose"
    @closed="onClosed"
  >
    <template v-if="detail">
      <div class="status-row">
        <el-tag
          :type="detail.customized ? 'warning' : 'info'"
          size="small"
          data-test="prompt-status"
        >
          {{ detail.customized ? '已自定义' : '默认' }}
        </el-tag>
        <span class="hint">模板将随每次运行发送至已配置的大模型服务；修改只影响其后新发起的运行。</span>
      </div>

      <el-form label-width="90px" class="editor-form">
        <el-form-item label="提示词模板">
          <el-input
            ref="inputRef"
            v-model="content"
            type="textarea"
            :rows="12"
            data-test="prompt-textarea"
          />
          <div class="counter" :class="{ over: overLimit }" data-test="prompt-counter">
            {{ content.length }} / {{ detail.max_length }} 字符
          </div>
        </el-form-item>

        <el-form-item label="可用变量">
          <div class="vars">
            <div class="var-list">
              <el-button
                v-for="v in allVariables"
                :key="v.name"
                size="small"
                plain
                :data-test="`prompt-var-${v.name}`"
                @click="insertVariable(v.name)"
              >
                {{ '{' + v.name + '}' }}
              </el-button>
            </div>
            <div v-for="v in allVariables" :key="`desc-${v.name}`" class="var-desc">
              <code>{{ '{' + v.name + '}' }}</code>
              <span>{{ v.label }}：{{ v.render }}</span>
            </div>
          </div>
        </el-form-item>

        <el-form-item label="固定结构">
          <div class="contract">
            <div class="hint">「{output_contract}」槽位处将替换为以下内容（系统固定，不可修改）</div>
            <pre class="contract-text" data-test="prompt-contract">{{ detail.output_contract }}</pre>
          </div>
        </el-form-item>
      </el-form>
    </template>

    <template #footer>
      <el-button data-test="prompt-close" @click="attemptClose">关闭</el-button>
      <el-button
        data-test="prompt-reset"
        :disabled="!detail?.customized || busy"
        @click="onReset"
      >
        恢复默认
      </el-button>
      <el-button
        type="primary"
        :loading="saving"
        :disabled="!detail || loading"
        data-test="prompt-save"
        @click="onSave"
      >
        保存
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { InputInstance } from 'element-plus'
import { getPrompt, resetPrompt, savePrompt } from '../../api/prompts'
import type { PromptFeatureKey, PromptTemplateDetail, PromptVariable } from '../../api/types'

const emit = defineEmits<{ changed: [feature: PromptFeatureKey] }>()

const visible = ref(false)
const loading = ref(false)
const saving = ref(false)
const busy = ref(false)
const feature = ref<PromptFeatureKey>('seed_expand')
const detail = ref<PromptTemplateDetail | null>(null)
const content = ref('')
const inputRef = ref<InputInstance | null>(null)

const allVariables = computed<PromptVariable[]>(() =>
  detail.value ? [...detail.value.variables, ...detail.value.reserved_variables] : [],
)
const overLimit = computed(() => !!detail.value && content.value.length > detail.value.max_length)
const dirty = computed(() => detail.value !== null && content.value !== detail.value.content)

async function open(key: PromptFeatureKey) {
  feature.value = key
  visible.value = true
  loading.value = true
  detail.value = null
  try {
    detail.value = await getPrompt(key)
    content.value = detail.value.content
  } catch {
    /* 统一错误提示已由客户端弹出 */
    visible.value = false
  } finally {
    loading.value = false
  }
}

function onClosed() {
  detail.value = null
  content.value = ''
  saving.value = false
}

function textareaEl(): HTMLTextAreaElement | null {
  const el = inputRef.value as unknown as { textarea?: HTMLTextAreaElement } | null
  return el?.textarea ?? null
}

/** 变量按钮：在光标处插入 {token}（无光标信息时追加到末尾） */
function insertVariable(name: string) {
  const token = `{${name}}`
  const ta = textareaEl()
  if (!ta) {
    content.value += token
    return
  }
  const start = ta.selectionStart ?? content.value.length
  const end = ta.selectionEnd ?? start
  content.value = content.value.slice(0, start) + token + content.value.slice(end)
  const pos = start + token.length
  nextTick(() => {
    ta.focus()
    ta.setSelectionRange(pos, pos)
  })
}

/** 客户端同规则预检（体验用；服务端 PUT 响应为权威——contract §7） */
const UNKNOWN_RE = /(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})/g

function precheckWarnings(): { code: string; message: string }[] {
  const d = detail.value
  if (!d) return []
  const known = new Set(allVariables.value.map((v) => v.name))
  const warnings: { code: string; message: string }[] = []
  const seen = new Set<string>()
  for (const match of content.value.matchAll(UNKNOWN_RE)) {
    const name = match[1]
    if (!known.has(name) && !seen.has(name)) {
      seen.add(name)
      warnings.push({
        code: 'unknown_variable',
        message: `未识别的变量 {${name}}：该处将按原文发送，建议改名或删除`,
      })
    }
  }
  for (const v of d.variables) {
    if (!content.value.includes(`{${v.name}}`)) {
      warnings.push({
        code: 'missing_variable',
        message: `未引用 {${v.name}}（${v.label}）：对应表单内容将不再发送给模型`,
      })
    }
  }
  if (!content.value.includes('{output_contract}')) {
    warnings.push({
      code: 'missing_output_contract',
      message: '未包含 {output_contract} 输出结构槽位：运行时会自动补充在末尾',
    })
  }
  return warnings
}

async function onSave() {
  const d = detail.value
  if (!d || saving.value) return
  if (!content.value.trim()) {
    ElMessage.warning('提示词不能为空')
    return
  }
  if (content.value.length > d.max_length) {
    ElMessage.warning(`超过长度上限（${content.value.length}/${d.max_length} 字符）`)
    return
  }
  const warnings = precheckWarnings()
  if (warnings.length) {
    try {
      await ElMessageBox.confirm(
        `保存前提示：\n${warnings.map((w) => `· ${w.message}`).join('\n')}`,
        '仍要保存？',
        { confirmButtonText: '仍要保存', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }
  }
  saving.value = true
  try {
    detail.value = await savePrompt(feature.value, content.value)
    content.value = detail.value.content
    for (const w of detail.value.warnings ?? []) ElMessage.warning(w.message)
    ElMessage.success('提示词已保存（对下一次运行生效）')
    emit('changed', feature.value)
  } catch {
    /* 统一错误提示已由客户端弹出 */
  } finally {
    saving.value = false
  }
}

async function onReset() {
  const d = detail.value
  if (!d || !d.customized || busy.value) return
  try {
    await ElMessageBox.confirm(
      '恢复默认将丢弃当前自定义模板，之后的运行改用内置默认提示词。',
      '恢复默认？',
      { confirmButtonText: '恢复默认', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  busy.value = true
  try {
    detail.value = await resetPrompt(feature.value)
    content.value = detail.value.content
    ElMessage.success('已恢复默认提示词')
    emit('changed', feature.value)
  } catch {
    /* 统一错误提示已由客户端弹出 */
  } finally {
    busy.value = false
  }
}

/** 脏状态关闭需确认放弃（X / ESC / 遮罩经 dialog before-close；页脚按钮直接走本函数） */
async function handleBeforeClose(done: () => void) {
  if (!dirty.value) {
    done()
    return
  }
  try {
    await ElMessageBox.confirm('编辑器中有未保存的修改，关闭将丢弃。', '放弃未保存的修改？', {
      confirmButtonText: '放弃修改',
      cancelButtonText: '继续编辑',
      type: 'warning',
    })
    done()
  } catch {
    /* 留在编辑器 */
  }
}

function attemptClose() {
  void handleBeforeClose(() => {
    visible.value = false
  })
}

defineExpose({ open, visible, content, dirty })
</script>

<style scoped>
.status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.counter {
  width: 100%;
  text-align: right;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.counter.over {
  color: var(--el-color-danger);
}
.vars {
  width: 100%;
}
.var-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 6px;
}
.var-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}
.var-desc code {
  margin-right: 4px;
}
.contract {
  width: 100%;
}
.contract-text {
  margin: 4px 0 0;
  padding: 8px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
