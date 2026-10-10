<template>
  <div>
    <PageHeader
      title="营销内容"
      description="内容主题与多语言版本（中文母版为源）。未发布版本不能被营销计划选用（先审后发）。"
    >
      <template #actions>
        <el-button type="primary" @click="openCreate">新建主题</el-button>
        <el-button @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="themes" @expand-change="onExpand">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand-wrap">
              <div class="expand-actions">
                <el-button size="small" @click="openCreateVariant(row as ContentThemeRow)">新建语言版本</el-button>
                <el-button size="small" type="primary" plain @click="openAiDialog(row as ContentThemeRow)">AI 起草 / 多语言生成</el-button>
                <el-button size="small" @click="openCompare(row as ContentThemeRow)">多语言对照</el-button>
              </div>
              <el-table :data="variantsByTheme[row.id as number] || []" size="small">
                <el-table-column label="语言" width="90">
                  <template #default="{ row: variant }">{{ langLabel((variant as ContentVariantRow).lang) }}</template>
                </el-table-column>
                <el-table-column label="状态" width="100">
                  <template #default="{ row: variant }"><StatusTag :status="(variant as ContentVariantRow).status" /></template>
                </el-table-column>
                <el-table-column label="来源" width="110">
                  <template #default="{ row: variant }">{{ SOURCE_LABELS[(variant as ContentVariantRow).source] || (variant as ContentVariantRow).source }}</template>
                </el-table-column>
                <el-table-column label="当前版本" width="90">
                  <template #default="{ row: variant }">v{{ (variant as ContentVariantRow).current?.version_no ?? '—' }}</template>
                </el-table-column>
                <el-table-column label="变量" min-width="160">
                  <template #default="{ row: variant }">
                    <el-tag v-for="name in (variant as ContentVariantRow).current?.variables || []" :key="name" size="small" class="chip">{{ name }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="340" fixed="right">
                  <template #default="{ row: variant }">
                    <el-button size="small" text type="primary" @click="editVariant(variant as ContentVariantRow)">编辑内容</el-button>
                    <el-button size="small" text @click="viewHistory(variant as ContentVariantRow)">版本历史</el-button>
                    <el-button
                      v-if="(variant as ContentVariantRow).status !== 'published'"
                      size="small" text type="success"
                      @click="setStatus(variant as ContentVariantRow, 'published')"
                    >
                      发布
                    </el-button>
                    <el-button
                      v-else
                      size="small" text type="warning"
                      @click="setStatus(variant as ContentVariantRow, 'draft')"
                    >
                      退草稿
                    </el-button>
                    <el-button
                      v-if="(variant as ContentVariantRow).status === 'published'"
                      size="small" text
                      @click="setStatus(variant as ContentVariantRow, 'archived')"
                    >
                      归档
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
              <EmptyState
                v-if="(variantsByTheme[row.id as number] || []).length === 0"
                description="尚无语言版本：可手工新建或用 AI 生成多语言版本"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="主题" min-width="200" show-overflow-tooltip />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">{{ TYPE_LABELS[row.content_type] || row.content_type }}</template>
        </el-table-column>
        <el-table-column label="母版语言" width="100">
          <template #default="{ row }">{{ langLabel(row.master_lang) }}</template>
        </el-table-column>
        <el-table-column prop="variants_count" label="语言版本" width="90" />
        <el-table-column prop="description" label="备注" min-width="180" show-overflow-tooltip />
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ (row.created_at || '').slice(0, 19).replace('T', ' ') }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="danger" @click="removeTheme(row as ContentThemeRow)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="createVisible" title="新建内容主题" width="520px">
      <el-form label-width="100px">
        <el-form-item label="主题名称" required><el-input v-model="form.name" placeholder="如：首轮开发信 / 第二轮跟进" /></el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.content_type">
            <el-radio-button value="email">邮件</el-radio-button>
            <el-radio-button value="sms">短信</el-radio-button>
            <el-radio-button value="social_message">社媒消息</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="母版语言">
          <el-select v-model="form.master_lang" style="width: 100%">
            <el-option v-for="lang in LANGS" :key="lang.code" :value="lang.code" :label="`${lang.label}（${lang.code}）`" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="variantVisible" :title="`新建语言版本 · ${variantTarget?.name ?? ''}`" width="560px">
      <el-form label-width="100px">
        <el-form-item label="语言" required>
          <el-select v-model="variantForm.lang" style="width: 100%">
            <el-option
              v-for="lang in variantLangOptions"
              :key="lang.code"
              :value="lang.code"
              :label="`${lang.label}（${lang.code}）`"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="variantTarget?.content_type === 'email'" label="主题行">
          <el-input v-model="variantForm.subject" placeholder="可留空，稍后编辑" maxlength="200" />
        </el-form-item>
        <el-form-item label="正文">
          <el-input v-model="variantForm.body_md" type="textarea" :rows="6" placeholder="可留空，稍后在编辑器中撰写（支持 {{company_name}} 等变量）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="variantVisible = false">取消</el-button>
        <el-button type="primary" @click="submitVariant">创建并编辑</el-button>
      </template>
    </el-dialog>

    <AiContentDialog ref="aiDialogRef" @done="reloadVariants" />
    <CompareDialog ref="compareRef" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../../api/client'
import type { ContentThemeRow, ContentVariantRow } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import EmptyState from '../../components/common/EmptyState.vue'
import AiContentDialog from './AiContentDialog.vue'
import CompareDialog from './CompareDialog.vue'
import { LANGS, langLabel } from '../../constants'
import { useAiGate } from '../../composables/useAiGate'

const TYPE_LABELS: Record<string, string> = {
  email: '邮件',
  sms: '短信',
  social_message: '社媒消息',
}
const SOURCE_LABELS: Record<string, string> = {
  manual: '手工',
  llm_assisted: 'AI 辅助编写',
  llm_translated: 'AI 翻译',
}

const router = useRouter()
const { requireAi } = useAiGate()
const themes = ref<ContentThemeRow[]>([])
const variantsByTheme = ref<Record<number, ContentVariantRow[]>>({})
const loading = ref(false)
const createVisible = ref(false)
const form = ref({ name: '', content_type: 'email', master_lang: 'zh', description: '' })

const variantVisible = ref(false)
const variantTarget = ref<ContentThemeRow | null>(null)
const variantForm = ref({ lang: '', subject: '', body_md: '' })
const aiDialogRef = ref<InstanceType<typeof AiContentDialog> | null>(null)
const compareRef = ref<InstanceType<typeof CompareDialog> | null>(null)

const variantLangOptions = computed(() => {
  const existing = new Set(
    (variantTarget.value ? variantsByTheme.value[variantTarget.value.id] || [] : []).map(
      (variant) => variant.lang,
    ),
  )
  return LANGS.filter((lang) => !existing.has(lang.code))
})

async function load() {
  loading.value = true
  try {
    themes.value = await api.get<ContentThemeRow[]>('/content/themes')
  } finally {
    loading.value = false
  }
}

async function reloadVariants() {
  if (!variantTarget.value) {
    await load()
    return
  }
  const themeId = variantTarget.value.id
  variantsByTheme.value[themeId] = await api.get<ContentVariantRow[]>(
    `/content/themes/${themeId}/variants`,
  )
  await load()
}

async function onExpand(row: ContentThemeRow, expanded: boolean | ContentThemeRow[]) {
  const isExpanded = Array.isArray(expanded)
    ? expanded.some((item) => item.id === row.id)
    : expanded
  if (isExpanded) {
    variantsByTheme.value[row.id] = await api.get<ContentVariantRow[]>(
      `/content/themes/${row.id}/variants`,
    )
  }
}

function openCreate() {
  form.value = { name: '', content_type: 'email', master_lang: 'zh', description: '' }
  createVisible.value = true
}

async function submitCreate() {
  if (!form.value.name.trim()) {
    ElMessage.warning('请填写主题名称')
    return
  }
  await api.post('/content/themes', form.value)
  ElMessage.success('已创建（可在展开行中新建语言版本或使用 AI 生成）')
  createVisible.value = false
  await load()
}

function openCreateVariant(theme: ContentThemeRow) {
  variantTarget.value = theme
  variantForm.value = { lang: '', subject: '', body_md: '' }
  variantVisible.value = true
}

async function submitVariant() {
  if (!variantTarget.value) return
  if (!variantForm.value.lang) {
    ElMessage.warning('请选择语言')
    return
  }
  const variant = await api.post<ContentVariantRow>(
    `/content/themes/${variantTarget.value.id}/variants`,
    variantForm.value,
  )
  variantVisible.value = false
  ElMessage.success('语言版本已创建')
  await reloadVariants()
  router.push(`/content/variants/${variant.id}`)
}

async function openAiDialog(theme: ContentThemeRow) {
  if (!(await requireAi())) return
  variantTarget.value = theme
  aiDialogRef.value?.open({
    id: theme.id,
    name: theme.name,
    master_lang: theme.master_lang,
  })
}

function openCompare(theme: ContentThemeRow) {
  compareRef.value?.open(theme.id)
}

function editVariant(variant: ContentVariantRow) {
  router.push(`/content/variants/${variant.id}`)
}

function viewHistory(variant: ContentVariantRow) {
  router.push(`/content/variants/${variant.id}/versions`)
}

async function setStatus(variant: ContentVariantRow, status: string) {
  if (status === 'published') {
    try {
      await ElMessageBox.confirm(
        '发布后该语言版本可被营销计划选用；改写会自动退回草稿。确认发布？',
        '发布内容版本',
        { type: 'warning', confirmButtonText: '发布', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  const path =
    status === 'published' ? 'publish' : status === 'archived' ? 'archive' : 'back-to-draft'
  await api.post(`/content/variants/${variant.id}/${path}`)
  ElMessage.success('已更新状态')
  variantsByTheme.value[variant.theme_id] = await api.get<ContentVariantRow[]>(
    `/content/themes/${variant.theme_id}/variants`,
  )
  await load()
}

async function removeTheme(row: ContentThemeRow) {
  try {
    await ElMessageBox.confirm(
      `删除主题「${row.name}」将同时删除其全部语言版本与版本历史。此操作不可恢复，确认删除？`,
      '删除内容主题',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  await api.del(`/content/themes/${row.id}`)
  ElMessage.success('已删除')
  await load()
}

onMounted(load)
</script>

<style scoped>
.expand-wrap {
  padding: 8px 24px 12px 48px;
}
.expand-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.chip {
  margin-right: 4px;
}
</style>
