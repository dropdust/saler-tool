<template>
  <el-dialog
    v-model="visible"
    :title="`AI 提示词 · ${detail?.label ?? ''}`"
    width="760px"
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
          {{ detail.customized ? detail.active_name : '默认' }}
        </el-tag>
        <span class="hint">模板将随每次运行发送至已配置的大模型服务；切换与修改只影响其后新发起的运行。</span>
      </div>

      <el-form label-width="90px" class="editor-form">
        <el-form-item label="当前模板">
          <div class="selector-row">
            <el-select
              :model-value="selectedId"
              data-test="prompt-select"
              style="width: 280px"
              @change="onSelect"
            >
              <el-option value="" label="内置默认（不可修改）" />
              <el-option v-for="t in detail.templates" :key="t.id" :value="t.id" :label="t.name" />
            </el-select>
            <el-button data-test="prompt-save-as" :disabled="busy" @click="onSaveAs">另存为</el-button>
            <el-button data-test="prompt-rename" :disabled="!isNamed || busy" @click="onRename">重命名</el-button>
            <el-button data-test="prompt-delete" :disabled="!isNamed || busy" @click="onDelete">删除</el-button>
          </div>
        </el-form-item>

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

        <el-form-item label="AI 辅助">
          <div class="assist">
            <div class="assist-row">
              <el-input
                v-model="assistIntent"
                class="assist-intent"
                placeholder="用一句话描述意图，例如：面向东非市场，重点发掘各国电力公司与 EPC 总包"
                maxlength="2000"
                data-test="assist-intent"
              />
              <el-button
                :loading="assistLoading"
                :disabled="busy"
                data-test="assist-generate"
                @click="onAssistGenerate"
              >
                AI 生成
              </el-button>
              <el-button
                :loading="assistLoading"
                :disabled="busy"
                data-test="assist-polish"
                @click="onAssistPolish"
              >
                AI 优化当前草稿
              </el-button>
            </div>
            <div v-if="assistSuggestion !== null" class="assist-suggestion" data-test="assist-suggestion">
              <div class="hint">建议（仅供对照；「采用」仅写入编辑器，记得保存才生效）：</div>
              <pre class="contract-text">{{ assistSuggestion }}</pre>
              <div v-if="assistNotes" class="hint" data-test="assist-notes">要点：{{ assistNotes }}</div>
              <div class="assist-actions">
                <el-button size="small" type="primary" plain data-test="assist-adopt" @click="adoptSuggestion">
                  采用
                </el-button>
                <el-button size="small" data-test="assist-discard" @click="discardSuggestion">
                  丢弃
                </el-button>
                <el-button size="small" link data-test="assist-view-calls" @click="viewAssistCalls">
                  查看调用明细
                </el-button>
              </div>
            </div>
          </div>
        </el-form-item>
      </el-form>
    </template>

    <template #footer>
      <el-button data-test="prompt-close" @click="attemptClose">关闭</el-button>
      <el-button
        data-test="prompt-restore-default"
        :disabled="!detail?.customized || busy"
        @click="onRestoreDefault"
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

  <!-- 辅助调用明细（T292；append-to-body 叠在编辑器上，按 operation 过滤） -->
  <LlmCallsDrawer ref="assistDrawer" />
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { InputInstance } from 'element-plus'
import {
  activateTemplate,
  assistPrompt,
  createTemplate,
  deleteTemplate,
  getPrompt,
  updateTemplate,
} from '../../api/prompts'
import type { PromptAssistPayload } from '../../api/prompts'
import type { PromptFeatureKey, PromptTemplateDetail, PromptVariable } from '../../api/types'
import LlmCallsDrawer from './LlmCallsDrawer.vue'

const emit = defineEmits<{ changed: [feature: PromptFeatureKey] }>()

const visible = ref(false)
const loading = ref(false)
const saving = ref(false)
const busy = ref(false)
const feature = ref<PromptFeatureKey>('seed_expand')
const detail = ref<PromptTemplateDetail | null>(null)
const content = ref('')
/** 选择器值：'' = 内置默认；其余为具名模板 id。选择即生效（契约 §8） */
const selectedId = ref('')
const inputRef = ref<InputInstance | null>(null)

const allVariables = computed<PromptVariable[]>(() =>
  detail.value ? [...detail.value.variables, ...detail.value.reserved_variables] : [],
)
const isNamed = computed(() => selectedId.value !== '')
const activeItem = computed(
  () => detail.value?.templates.find((t) => t.id === selectedId.value) ?? null,
)
const savedContent = computed(
  () => activeItem.value?.content ?? detail.value?.default_content ?? '',
)
const dirty = computed(() => detail.value !== null && content.value !== savedContent.value)
const overLimit = computed(() => !!detail.value && content.value.length > detail.value.max_length)

async function open(key: PromptFeatureKey) {
  feature.value = key
  visible.value = true
  loading.value = true
  detail.value = null
  try {
    applyDetail(await getPrompt(key))
  } catch {
    /* 统一错误提示已由客户端弹出 */
    visible.value = false
  } finally {
    loading.value = false
  }
}

/** 以服务端详情为准刷新全部状态（生效选择 + 编辑区） */
function applyDetail(d: PromptTemplateDetail) {
  detail.value = d
  selectedId.value = d.active_id ?? ''
  content.value = d.active_id
    ? (d.templates.find((t) => t.id === d.active_id)?.content ?? d.default_content)
    : d.default_content
}

function onClosed() {
  detail.value = null
  content.value = ''
  selectedId.value = ''
  saving.value = false
  busy.value = false
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

/** 客户端同规则预检（体验用；服务端响应 warnings 为权威——contract §7） */
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

/** 内容级前置检查（空/超长/警告确认）；通过返回 true */
async function passContentChecks(): Promise<boolean> {
  const d = detail.value
  if (!d) return false
  if (!content.value.trim()) {
    ElMessage.warning('提示词不能为空')
    return false
  }
  if (content.value.length > d.max_length) {
    ElMessage.warning(`超过长度上限（${content.value.length}/${d.max_length} 字符）`)
    return false
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
      return false
    }
  }
  return true
}

async function doActivate(target: string | null) {
  busy.value = true
  try {
    applyDetail(await activateTemplate(feature.value, target))
    emit('changed', feature.value)
  } catch {
    /* 统一错误提示已由客户端弹出；选择器随 model-value 回退 */
  } finally {
    busy.value = false
  }
}

/** 选择即生效（契约 §8）：脏状态先确认放弃；取消则选择器回退原值 */
async function onSelect(id: string) {
  if (id === selectedId.value || busy.value) return
  if (dirty.value) {
    try {
      await ElMessageBox.confirm('切换模板将丢弃编辑器中的未保存修改。', '放弃未保存的修改？', {
        confirmButtonText: '放弃并切换',
        cancelButtonText: '继续编辑',
        type: 'warning',
      })
    } catch {
      return
    }
  }
  await doActivate(id === '' ? null : id)
}

async function onSave() {
  if (!detail.value || saving.value || busy.value) return
  if (!(await passContentChecks())) return
  if (!isNamed.value) {
    // FR-015：内置默认不可改——保存引导另存为
    await doSaveAs()
    return
  }
  saving.value = true
  try {
    const next = await updateTemplate(feature.value, selectedId.value, { content: content.value })
    applyDetail(next)
    for (const w of next.warnings ?? []) ElMessage.warning(w.message)
    ElMessage.success('提示词已保存（对下一次运行生效）')
    emit('changed', feature.value)
  } catch {
    /* 统一错误提示已由客户端弹出 */
  } finally {
    saving.value = false
  }
}

/** 命名输入（另存为/重命名共用）；取消返回 null */
async function askName(title: string, initial: string): Promise<string | null> {
  try {
    const result = await ElMessageBox.prompt('模板名称（同功能内不得重名）', title, {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValue: initial,
      inputValidator: (value: string) => (value ?? '').trim() ? true : '名称不能为空',
    })
    return String(result.value).trim()
  } catch {
    return null
  }
}

async function doSaveAs() {
  const d = detail.value
  if (!d || busy.value) return
  const name = await askName('另存为新模板', '')
  if (name === null) return
  busy.value = true
  try {
    const next = await createTemplate(feature.value, {
      name,
      content: content.value,
      activate: true,
    })
    applyDetail(next)
    for (const w of next.warnings ?? []) ElMessage.warning(w.message)
    ElMessage.success(`已创建并启用：${name}`)
    emit('changed', feature.value)
  } catch {
    /* 统一错误提示已由客户端弹出 */
  } finally {
    busy.value = false
  }
}

async function onSaveAs() {
  if (!detail.value || busy.value || saving.value) return
  if (!(await passContentChecks())) return
  await doSaveAs()
}

async function onRename() {
  const d = detail.value
  if (!d || !isNamed.value || busy.value) return
  const name = await askName('重命名模板', activeItem.value?.name ?? '')
  if (name === null || name === activeItem.value?.name) return
  busy.value = true
  try {
    applyDetail(await updateTemplate(feature.value, selectedId.value, { name }))
    ElMessage.success('已重命名')
    emit('changed', feature.value)
  } catch {
    /* 统一错误提示已由客户端弹出 */
  } finally {
    busy.value = false
  }
}

async function onDelete() {
  const d = detail.value
  if (!d || !isNamed.value || busy.value) return
  try {
    await ElMessageBox.confirm(
      `删除模板「${activeItem.value?.name}」？若它是当前生效模板，将自动回到内置默认。`,
      '删除模板？',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  busy.value = true
  try {
    applyDetail(await deleteTemplate(feature.value, selectedId.value))
    ElMessage.success('已删除模板')
    emit('changed', feature.value)
  } catch {
    /* 统一错误提示已由客户端弹出 */
  } finally {
    busy.value = false
  }
}

async function onRestoreDefault() {
  if (!detail.value?.customized || busy.value) return
  try {
    await ElMessageBox.confirm('切回内置默认模板；已保存的自定义模板全部保留。', '恢复默认？', {
      confirmButtonText: '恢复默认',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  await doActivate(null)
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

// ---- AI 辅助（T292 / FR-009~012）：单轮生成或润色；建议态呈现，"采用"≠保存 ----

const assistIntent = ref('')
const assistLoading = ref(false)
const assistSuggestion = ref<string | null>(null)
const assistNotes = ref<string | null>(null)
const assistDrawer = ref<InstanceType<typeof LlmCallsDrawer> | null>(null)

async function onAssistGenerate() {
  const intent = assistIntent.value.trim()
  if (!intent) {
    ElMessage.warning('请先输入意图（一句话描述你想要的提示词方向）')
    return
  }
  await runAssist({ mode: 'generate', intent })
}

async function onAssistPolish() {
  if (!content.value.trim()) {
    ElMessage.warning('编辑器内容为空，无可优化的草稿')
    return
  }
  await runAssist({ mode: 'polish', draft: content.value })
}

async function runAssist(payload: PromptAssistPayload) {
  if (assistLoading.value) return
  assistLoading.value = true
  try {
    const resp = await assistPrompt(feature.value, payload)
    assistSuggestion.value = resp.suggestion
    assistNotes.value = resp.notes
  } catch (err) {
    // 编辑器内容无损（辅助失败仅影响建议区）；409 补一条前往配置的指引
    if ((err as { code?: string } | null)?.code === 'llm_not_configured') {
      ElMessage.warning('尚未配置大模型服务：请前往「设置 → 大模型」添加并测试后再试')
    }
  } finally {
    assistLoading.value = false
  }
}

/** 采用：建议写入编辑器（dirty）；绝不自动保存（FR-010——"采用"≠保存） */
function adoptSuggestion() {
  if (assistSuggestion.value === null) return
  content.value = assistSuggestion.value
  assistSuggestion.value = null
  assistNotes.value = null
  ElMessage.success('已采用建议（保存后才会对后续运行生效）')
}

function discardSuggestion() {
  assistSuggestion.value = null
  assistNotes.value = null
}

function viewAssistCalls() {
  assistDrawer.value?.open({ operation: 'prompt_assist', title: 'AI 调用明细 · 提示词辅助' })
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
.selector-row {
  display: flex;
  gap: 8px;
  width: 100%;
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
.assist {
  width: 100%;
}
.assist-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.assist-intent {
  flex: 1;
}
.assist-suggestion {
  margin-top: 8px;
}
.assist-actions {
  margin-top: 6px;
}
</style>
