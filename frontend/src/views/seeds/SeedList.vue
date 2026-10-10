<template>
  <div>
    <PageHeader
      title="种子列表"
      description="结构化搜索词：手工 / 大模型扩充 / 检索发现；采纳后进入执行与产量归因。"
    >
      <template #actions>
        <el-button type="primary" @click="openCreate">新建种子</el-button>
        <el-button type="success" plain @click="aiDialog?.open()">AI 扩充</el-button>
        <el-button :disabled="!selected.length" @click="openTranslate">
          翻译选中（{{ selected.length }}）
        </el-button>
        <el-button @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <el-card shadow="never" class="filters">
      <el-form inline>
        <el-form-item label="搜索词">
          <el-input v-model="filters.q" clearable style="width: 190px" @keyup.enter="load" />
        </el-form-item>
        <el-form-item label="执行状态">
          <el-select v-model="filters.status" clearable style="width: 120px">
            <el-option label="待执行" value="pending" />
            <el-option label="执行中" value="running" />
            <el-option label="已完成" value="done" />
            <el-option label="已失效" value="invalid" />
          </el-select>
        </el-form-item>
        <el-form-item label="审核">
          <el-select v-model="filters.review_status" clearable style="width: 110px">
            <el-option label="已采纳" value="approved" />
            <el-option label="待审核" value="pending" />
            <el-option label="已拒绝" value="rejected" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源">
          <el-select v-model="filters.source" clearable style="width: 110px">
            <el-option v-for="(label, key) in SOURCE_LABELS" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="批次">
          <el-input v-model="filters.batch" clearable style="width: 130px" />
        </el-form-item>
        <el-form-item label="排序">
          <el-select v-model="filters.sort" style="width: 110px">
            <el-option label="优先级" value="priority" />
            <el-option label="产量" value="yield" />
            <el-option label="最新" value="created" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="items" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="42" />
        <el-table-column prop="query" label="搜索词" min-width="240" show-overflow-tooltip />
        <el-table-column label="分类" min-width="190">
          <template #default="{ row }">
            <el-tag v-if="row.product_line_id" size="small" class="chip">{{ nodeName(row.product_line_id) }}</el-tag>
            <el-tag v-if="row.persona_id" size="small" type="warning" class="chip">{{ nodeName(row.persona_id) }}</el-tag>
            <el-tag v-if="row.market_id" size="small" type="info" class="chip">{{ nodeName(row.market_id) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="语言" width="70">
          <template #default="{ row }">{{ langLabel(row.lang) }}</template>
        </el-table-column>
        <el-table-column label="优先级" width="76">
          <template #default="{ row }">{{ PRIORITY_LABELS[row.priority] ?? row.priority }}</template>
        </el-table-column>
        <el-table-column prop="batch" label="批次" width="140" show-overflow-tooltip />
        <el-table-column label="状态" width="86">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="审核" width="86">
          <template #default="{ row }"><StatusTag :status="row.review_status" /></template>
        </el-table-column>
        <el-table-column prop="n_candidates" label="候选" width="64" />
        <el-table-column prop="n_contacts" label="联系方式" width="82" />
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text @click="openEdit(row as Seed)">编辑</el-button>
            <el-button size="small" text type="danger" @click="disable(row as Seed)">失效</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="page"
        class="pager"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        @current-change="load"
      />
    </el-card>

    <AiExpandDialog ref="aiDialog" @done="load" />

    <el-dialog v-model="createVisible" title="新建种子" width="540px">
      <el-form label-width="90px">
        <el-form-item label="搜索词" required>
          <el-input v-model="createForm.query" placeholder="可直接用于搜索引擎的检索词" />
        </el-form-item>
        <el-form-item label="语言">
          <el-select v-model="createForm.lang" style="width: 100%">
            <el-option v-for="l in LANGS" :key="l.code" :value="l.code" :label="`${l.label}（${l.code}）`" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-radio-group v-model="createForm.priority">
            <el-radio-button :value="1">高</el-radio-button>
            <el-radio-button :value="2">中</el-radio-button>
            <el-radio-button :value="3">低</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="产品线">
          <el-select v-model="createForm.product_line_id" clearable filterable style="width: 100%">
            <el-option v-for="n in nodesOf('product_line')" :key="n.id" :value="n.id" :label="n.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="客户角色">
          <el-select v-model="createForm.persona_id" clearable filterable style="width: 100%">
            <el-option v-for="n in nodesOf('persona')" :key="n.id" :value="n.id" :label="n.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="市场">
          <el-select v-model="createForm.market_id" clearable filterable style="width: 100%">
            <el-option v-for="n in nodesOf('market')" :key="n.id" :value="n.id" :label="n.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="批次">
          <el-input v-model="createForm.batch" placeholder="如 manual-1" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="createForm.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editVisible" title="编辑种子" width="480px">
      <el-form v-if="editForm" label-width="90px">
        <el-form-item label="搜索词"><el-input :model-value="editForm.query" disabled /></el-form-item>
        <el-form-item label="优先级">
          <el-radio-group v-model="editForm.priority">
            <el-radio-button :value="1">高</el-radio-button>
            <el-radio-button :value="2">中</el-radio-button>
            <el-radio-button :value="3">低</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="批次"><el-input v-model="editForm.batch" /></el-form-item>
        <el-form-item label="执行状态">
          <el-select v-model="editForm.status" style="width: 100%">
            <el-option label="待执行" value="pending" />
            <el-option label="完成" value="done" />
            <el-option label="失效" value="invalid" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="editForm.note" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="translateVisible" title="翻译种子（结果进入待审核）" width="520px">
      <p class="hint">
        将对选中的 {{ selected.length }} 条种子执行大模型翻译（建议选择中文种子）。
        产出为待审核状态，采纳后方可导出执行。
      </p>
      <el-select v-model="translateTargets" multiple style="width: 100%" placeholder="选择目标语言">
        <el-option v-for="l in LANGS" :key="l.code" :value="l.code" :label="`${l.label}（${l.code}）`" />
      </el-select>
      <template #footer>
        <el-button @click="translateVisible = false">取消</el-button>
        <el-button type="primary" :loading="translating" @click="doTranslate">开始翻译</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import { watchJob } from '../../api/jobs'
import type { GraphNode, Paginated, Seed } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import AiExpandDialog from './AiExpandDialog.vue'
import { LANGS, PRIORITY_LABELS, SOURCE_LABELS, langLabel } from '../../constants'

const filters = ref({
  q: '',
  status: '',
  review_status: 'approved',
  source: '',
  batch: '',
  sort: 'priority',
  market_id: null as number | null,
})
const items = ref<Seed[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)
const selected = ref<Seed[]>([])
const nodes = ref<GraphNode[]>([])
const aiDialog = ref<InstanceType<typeof AiExpandDialog>>()

const nodesById = computed(() => {
  const map: Record<number, GraphNode> = {}
  for (const node of nodes.value) map[node.id] = node
  return map
})

function nodeName(id: number | null): string {
  return id ? (nodesById.value[id]?.name ?? `#${id}`) : ''
}

function nodesOf(type: string): GraphNode[] {
  return nodes.value.filter((node) => node.node_type === type && node.status === 'active')
}

function onSelectionChange(rows: Seed[]) {
  selected.value = rows
}

async function loadNodes() {
  const result = await api.get<Paginated<GraphNode>>('/graph/nodes', { page_size: 500 })
  nodes.value = result.items
}

async function load() {
  loading.value = true
  try {
    const result = await api.get<Paginated<Seed>>('/seeds', {
      ...filters.value,
      page: page.value,
      page_size: pageSize,
    })
    items.value = result.items
    total.value = result.total
    selected.value = []
  } finally {
    loading.value = false
  }
}

// ---- 新建 / 编辑 / 失效 ----
const createVisible = ref(false)
const createForm = ref({
  query: '',
  lang: 'en',
  priority: 2,
  product_line_id: null as number | null,
  persona_id: null as number | null,
  market_id: null as number | null,
  batch: '',
  note: '',
})

function openCreate() {
  createForm.value = {
    query: '',
    lang: 'en',
    priority: 2,
    product_line_id: null,
    persona_id: null,
    market_id: null,
    batch: '',
    note: '',
  }
  createVisible.value = true
}

async function submitCreate() {
  if (!createForm.value.query.trim()) {
    ElMessage.warning('请填写搜索词')
    return
  }
  await api.post('/seeds', { ...createForm.value, batch: createForm.value.batch || null })
  ElMessage.success('已创建')
  createVisible.value = false
  await load()
}

const editVisible = ref(false)
const editForm = ref<Seed | null>(null)

function openEdit(row: Seed) {
  editForm.value = { ...row }
  editVisible.value = true
}

async function submitEdit() {
  if (!editForm.value) return
  await api.put(`/seeds/${editForm.value.id}`, {
    priority: editForm.value.priority,
    batch: editForm.value.batch || null,
    status: editForm.value.status,
    note: editForm.value.note,
  })
  ElMessage.success('已保存')
  editVisible.value = false
  await load()
}

async function disable(row: Seed) {
  await api.del(`/seeds/${row.id}`)
  ElMessage.success('已置为失效')
  await load()
}

// ---- 翻译 ----
const translateVisible = ref(false)
const translateTargets = ref<string[]>([])
const translating = ref(false)

function openTranslate() {
  translateTargets.value = []
  translateVisible.value = true
}

async function doTranslate() {
  if (!translateTargets.value.length) {
    ElMessage.warning('请选择目标语言')
    return
  }
  translating.value = true
  try {
    const { job_id } = await api.post<{ job_id: number }>('/ai/seeds/translate', {
      seed_ids: selected.value.map((row) => row.id),
      targets: translateTargets.value,
    })
    const job = await watchJob(job_id)
    if (job.status === 'completed') {
      const created = (job.result?.created as number) ?? 0
      ElMessage.success(`翻译完成：新增 ${created} 条（待审核）`)
      translateVisible.value = false
      await load()
    } else {
      ElMessage.error(job.error ?? '翻译失败')
    }
  } finally {
    translating.value = false
  }
}

onMounted(async () => {
  const route = useRoute()
  if (route.query.market_id) {
    filters.value.market_id = Number(route.query.market_id)
  }
  await loadNodes()
  await load()
})
</script>

<style scoped>
.filters {
  margin-bottom: 12px;
}
.filters :deep(.el-form-item) {
  margin-bottom: 8px;
}
.chip {
  margin-right: 4px;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin: 0 0 12px;
}
</style>
