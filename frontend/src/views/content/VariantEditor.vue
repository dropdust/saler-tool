<template>
  <div v-loading="loading">
    <PageHeader
      :title="`内容编辑 · ${langLabel(variant?.lang)}`"
      :description="`${themeName || '主题'}｜当前 v${current?.version_no ?? '—'}｜保存即生成新版本（审计链完整）`"
    >
      <template #actions>
        <el-button @click="goBack">返回列表</el-button>
        <el-button @click="goHistory">版本历史</el-button>
        <el-button
          v-if="variant && variant.status !== 'published'"
          type="success"
          @click="setStatus('publish')"
        >
          发布
        </el-button>
        <el-button v-else type="warning" @click="setStatus('back-to-draft')">退回草稿</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存（新版本）</el-button>
      </template>
    </PageHeader>

    <el-alert
      v-if="variant && variant.status === 'published'"
      type="warning"
      :closable="false"
      show-icon
      class="mb"
      title="该语言版本已发布：保存修改会自动退回草稿，需重新发布后营销计划才会选用。"
    />

    <el-row :gutter="16">
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span>编辑（Markdown）</span>
              <span class="hint">变量语法：<code>{{ varSyntax }}</code></span>
            </div>
          </template>
          <el-form label-width="70px">
            <el-form-item v-if="contentType === 'email'" label="主题行">
              <el-input v-model="form.subject" placeholder="邮件主题（可含变量）" maxlength="200" />
            </el-form-item>
            <el-form-item label="变量">
              <div class="var-bar">
                <el-button
                  v-for="name in availableVariables"
                  :key="name"
                  size="small"
                  plain
                  @click="insertVariable(name)"
                >
                  {{ name }}
                </el-button>
              </div>
            </el-form-item>
            <el-form-item label="正文">
              <el-input
                ref="bodyRef"
                v-model="form.body"
                type="textarea"
                :rows="18"
                placeholder="正文内容（Markdown，支持 {{company_name}} 等变量）"
              />
            </el-form-item>
            <el-form-item label="变更说明">
              <el-input v-model="form.change_note" placeholder="可留空（默认「内容修改」）" maxlength="200" />
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="10">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span>预览（变量已代入）</span>
              <el-button size="small" text type="primary" @click="refreshPreview">刷新</el-button>
            </div>
          </template>
          <div v-if="preview">
            <div v-if="contentType === 'email'" class="preview-subject">
              <span class="label">主题行：</span>{{ preview.subject || '（空）' }}
            </div>
            <pre class="preview-body">{{ preview.body || '（空）' }}</pre>
            <el-alert
              v-for="(warning, index) in preview.warnings"
              :key="index"
              type="warning"
              :closable="false"
              show-icon
              class="mb-sm"
              :title="warning"
            />
            <el-alert
              v-if="!preview.warnings.length"
              type="success"
              :closable="false"
              show-icon
              title="变量完整，无告警"
            />
          </div>
          <EmptyState v-else description="保存后即可预览" />

          <el-divider>
            <span class="hint">示例变量值（仅用于预览）</span>
          </el-divider>
          <el-form label-width="110px" size="small">
            <el-form-item
              v-for="name in usedVariables"
              :key="name"
              :label="name"
            >
              <el-input v-model="sampleVars[name]" :placeholder="SAMPLE_HINTS[name] || '示例值'" />
            </el-form-item>
            <div v-if="!usedVariables.length" class="hint">正文中尚未使用变量</div>
            <el-form-item v-if="!usedVariables.length">
              <el-select
                v-model="companyId"
                clearable
                filterable
                placeholder="或选择客户带入真实资料"
                style="width: 100%"
                @change="refreshPreview"
              >
                <el-option
                  v-for="company in companies"
                  :key="company.id"
                  :value="company.id"
                  :label="company.name || company.domain || `#${company.id}`"
                />
              </el-select>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../../api/client'
import type { CompanyRow, ContentThemeRow, ContentVariantRow, Paginated } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import EmptyState from '../../components/common/EmptyState.vue'
import { langLabel } from '../../constants'

/** 后端内置变量（render.py BUILTIN_VARIABLES），另加历史版本已用变量。 */
const BUILTIN_VARIABLES = [
  'company_name',
  'contact_name',
  'country',
  'language',
  'sender_name',
  'signature',
  'today',
]
/** 模板内字符串字面量不能含 `{{`（会被解析为插值），经数据传入。 */
const varSyntax = '{{变量名}}'
const SAMPLE_HINTS: Record<string, string> = {
  company_name: '如：AL-FARID Trading Co.',
  contact_name: '如：Ahmed',
  country: '如：Kenya',
  language: '如：English',
  sender_name: '发件人姓名',
  signature: '落款（公司/联系方式）',
  today: '2026-10-10',
}

const route = useRoute()
const router = useRouter()
const variantId = Number(route.params.id)

const loading = ref(false)
const saving = ref(false)
const variant = ref<ContentVariantRow | null>(null)
const themeName = ref('')
const contentType = ref('email')
const companies = ref<CompanyRow[]>([])
const companyId = ref<number | null>(null)
const sampleVars = ref<Record<string, string>>({})
const preview = ref<{ subject: string; body: string; warnings: string[] } | null>(null)
const bodyRef = ref<{ textarea?: HTMLTextAreaElement } | null>(null)

const form = ref({ subject: '', body: '', change_note: '' })
let loadedSnapshot = ''

const current = computed(() => variant.value?.current ?? null)
const usedVariables = computed(() => {
  const names = [...(current.value?.variables ?? [])]
  for (const match of form.value.body.matchAll(/\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g)) {
    const name = match[1].toLowerCase()
    if (!names.includes(name)) names.push(name)
  }
  return names
})
const availableVariables = computed(() => {
  const merged = [...BUILTIN_VARIABLES]
  for (const name of usedVariables.value) if (!merged.includes(name)) merged.push(name)
  return merged
})

function snapshot(): string {
  return JSON.stringify({ subject: form.value.subject, body: form.value.body })
}

async function load() {
  loading.value = true
  try {
    variant.value = await api.get<ContentVariantRow>(`/content/variants/${variantId}`)
    const theme = await api.get<ContentThemeRow>(`/content/themes/${variant.value.theme_id}`)
    themeName.value = theme.name
    contentType.value = theme.content_type
    form.value = {
      subject: current.value?.subject ?? '',
      body: current.value?.body_md ?? '',
      change_note: '',
    }
    loadedSnapshot = snapshot()
    await refreshPreview()
  } finally {
    loading.value = false
  }
}

/** 从光标处插入变量；textarea 场景按选区追加。 */
function insertVariable(name: string) {
  const textarea = bodyRef.value?.textarea
  const token = `{{${name}}}`
  if (textarea) {
    const start = textarea.selectionStart ?? form.value.body.length
    const end = textarea.selectionEnd ?? start
    form.value.body = form.value.body.slice(0, start) + token + form.value.body.slice(end)
    nextTick(() => {
      textarea.focus()
      textarea.setSelectionRange(start + token.length, start + token.length)
    })
  } else {
    form.value.body += token
  }
}

async function refreshPreview() {
  if (!current.value) return
  const vars: Record<string, string> = {}
  for (const [key, value] of Object.entries(sampleVars.value)) if (value) vars[key] = value
  preview.value = await api.post(`/content/variants/${variantId}/preview`, {
    vars,
    company_id: companyId.value,
  })
}

let previewTimer: ReturnType<typeof setTimeout> | null = null
watch(
  () => [form.value.subject, form.value.body, sampleVars.value],
  () => {
    if (previewTimer) clearTimeout(previewTimer)
    previewTimer = setTimeout(refreshPreview, 600)
  },
  { deep: true },
)

async function save() {
  if (variant.value?.status === 'published') {
    try {
      await ElMessageBox.confirm(
        '该版本已发布：保存会生成新版本并退回草稿（需重新发布）。继续保存？',
        '已发布内容改写',
        { type: 'warning', confirmButtonText: '保存并退草稿', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  saving.value = true
  try {
    await api.put(`/content/variants/${variantId}`, {
      subject: contentType.value === 'email' ? form.value.subject : form.value.subject || null,
      body_md: form.value.body,
      change_note: form.value.change_note || undefined,
    })
    ElMessage.success('已保存为新版本')
    await load()
  } finally {
    saving.value = false
  }
}

async function setStatus(action: 'publish' | 'back-to-draft') {
  if (action === 'publish' && snapshot() !== loadedSnapshot) {
    ElMessage.warning('有未保存的修改：请先保存再发布')
    return
  }
  await api.post(`/content/variants/${variantId}/${action}`)
  ElMessage.success(action === 'publish' ? '已发布：营销计划可选用' : '已退回草稿')
  await load()
}

function goBack() {
  router.push('/content')
}
function goHistory() {
  router.push(`/content/variants/${variantId}/versions`)
}

async function loadCompanies() {
  try {
    const page = await api.get<Paginated<CompanyRow>>('/companies', { page_size: 200 })
    companies.value = page.items
  } catch {
    /* 预览可选手动变量，客户列表失败不阻断编辑 */
  }
}

onMounted(async () => {
  await load()
  await loadCompanies()
})
</script>

<style scoped>
.mb {
  margin-bottom: 12px;
}
.mb-sm {
  margin-bottom: 6px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.var-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.preview-subject {
  font-weight: 600;
  margin-bottom: 8px;
}
.preview-subject .label {
  color: var(--el-text-color-secondary);
  font-weight: 400;
}
.preview-body {
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 12px;
  margin: 0 0 12px;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.6;
}
</style>
