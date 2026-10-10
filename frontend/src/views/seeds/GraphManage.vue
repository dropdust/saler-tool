<template>
  <div>
    <PageHeader
      title="图谱管理"
      description="节点（产品线/客户角色/市场/机构实体）、词表与关系；AI 产出在此审核。"
    >
      <template #actions>
        <el-button type="primary" @click="openCreateDialog">新建节点</el-button>
        <el-button @click="openEdgeDialog">新建关系</el-button>
        <el-button @click="loadAll">刷新</el-button>
      </template>
    </PageHeader>

    <el-card shadow="never">
      <el-tabs v-model="activeTab">
        <el-tab-pane v-for="tab in nodeTabs" :key="tab.type" :label="tab.label" :name="tab.type">
          <el-table v-loading="loading" :data="nodesOf(tab.type)">
            <el-table-column prop="name" label="名称" min-width="220" show-overflow-tooltip />
            <el-table-column v-if="tab.type === 'market'" prop="region" label="大区" width="110" />
            <el-table-column label="来源" width="80">
              <template #default="{ row }">{{ SOURCE_LABELS[row.source] ?? row.source }}</template>
            </el-table-column>
            <el-table-column label="置信度" width="86">
              <template #default="{ row }">{{ row.confidence ?? '—' }}</template>
            </el-table-column>
            <el-table-column label="审核" width="170">
              <template #default="{ row }">
                <template v-if="row.review_status === 'pending'">
                  <el-button size="small" type="success" text @click="reviewNode(row as GraphNode, 'approve')">采纳</el-button>
                  <el-button size="small" type="danger" text @click="reviewNode(row as GraphNode, 'reject')">拒绝</el-button>
                </template>
                <StatusTag v-else :status="row.review_status" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="230" fixed="right">
              <template #default="{ row }">
                <el-button size="small" text @click="openTerms(row as GraphNode)">词表</el-button>
                <el-button size="small" text @click="openEditDialog(row as GraphNode)">编辑</el-button>
                <el-button size="small" text @click="openMergeDialog(row as GraphNode)">合并</el-button>
                <el-button size="small" text type="danger" @click="disableNode(row as GraphNode)">停用</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="关系" name="edges">
          <el-table v-loading="loadingEdges" :data="edges">
            <el-table-column label="起点" min-width="180">
              <template #default="{ row }">{{ nodeName(row.from_node_id) }}</template>
            </el-table-column>
            <el-table-column label="终点" min-width="180">
              <template #default="{ row }">{{ nodeName(row.to_node_id) }}</template>
            </el-table-column>
            <el-table-column label="关系" min-width="180">
              <template #default="{ row }">{{ RELATION_LABELS[row.relation_type] ?? row.relation_type }}</template>
            </el-table-column>
            <el-table-column label="来源" width="80">
              <template #default="{ row }">{{ SOURCE_LABELS[row.source] ?? row.source }}</template>
            </el-table-column>
            <el-table-column label="操作" width="90">
              <template #default="{ row }">
                <el-button size="small" text type="danger" @click="removeEdge(row as GraphEdge)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 新建/编辑节点 -->
    <el-dialog v-model="formVisible" :title="editingNode ? '编辑节点' : '新建节点'" width="480px">
      <el-form label-width="90px">
        <el-form-item label="类型">
          <el-select v-model="form.node_type" :disabled="!!editingNode" style="width: 100%">
            <el-option v-for="tab in nodeTabs" :key="tab.type" :value="tab.type" :label="tab.label" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" required><el-input v-model="form.name" /></el-form-item>
        <el-form-item v-if="form.node_type === 'market'" label="大区">
          <el-input v-model="form.region" placeholder="如 东非 / 中东 / 南亚" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" @click="submitNodeForm">保存</el-button>
      </template>
    </el-dialog>

    <!-- 合并节点 -->
    <el-dialog v-model="mergeVisible" title="合并重复节点（保留目标，其余并入后删除）" width="520px">
      <p class="hint">目标：{{ mergeTarget?.name }}（{{ NODE_TYPE_LABELS[mergeTarget?.node_type ?? ''] }}）</p>
      <el-select v-model="mergeSources" multiple filterable style="width: 100%" placeholder="选择要并入的节点">
        <el-option
          v-for="node in mergeCandidates"
          :key="node.id"
          :value="node.id"
          :label="node.name"
        />
      </el-select>
      <template #footer>
        <el-button @click="mergeVisible = false">取消</el-button>
        <el-button type="primary" @click="submitMerge">合并</el-button>
      </template>
    </el-dialog>

    <!-- 词表 -->
    <el-dialog v-model="termsVisible" :title="`词表 — ${termsNode?.name ?? ''}`" width="640px">
      <el-form inline>
        <el-form-item>
          <el-select v-model="termForm.lang" style="width: 140px">
            <el-option v-for="l in LANGS" :key="l.code" :value="l.code" :label="`${l.label}（${l.code}）`" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-input v-model="termForm.term" placeholder="词条（名称/别名/术语）" style="width: 220px" />
        </el-form-item>
        <el-form-item>
          <el-select v-model="termForm.term_type" style="width: 120px">
            <el-option label="名称" value="name" />
            <el-option label="别名" value="alias" />
            <el-option label="同义词" value="synonym" />
            <el-option label="术语" value="term" />
          </el-select>
        </el-form-item>
        <el-form-item><el-button type="primary" @click="addTerm">添加</el-button></el-form-item>
      </el-form>
      <el-table :data="terms" max-height="360">
        <el-table-column prop="lang" label="语言" width="70" />
        <el-table-column prop="term" label="词条" min-width="200" show-overflow-tooltip />
        <el-table-column label="类型" width="80">
          <template #default="{ row }">
            {{ { name: '名称', alias: '别名', synonym: '同义词', term: '术语' }[row.term_type as 'name'] ?? row.term_type }}
          </template>
        </el-table-column>
        <el-table-column label="来源" width="80">
          <template #default="{ row }">{{ SOURCE_LABELS[row.source] ?? row.source }}</template>
        </el-table-column>
        <el-table-column label="审核" width="160">
          <template #default="{ row }">
            <template v-if="row.review_status === 'pending'">
              <el-button size="small" type="success" text @click="reviewTerm(row as NodeTerm, 'approve')">采纳</el-button>
              <el-button size="small" type="danger" text @click="reviewTerm(row as NodeTerm, 'reject')">拒绝</el-button>
            </template>
            <StatusTag v-else :status="row.review_status" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button size="small" text type="danger" @click="removeTerm(row as NodeTerm)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 新建关系 -->
    <el-dialog v-model="edgeVisible" title="新建关系" width="520px">
      <el-form label-width="90px">
        <el-form-item label="起点">
          <el-select v-model="edgeForm.from_node_id" filterable style="width: 100%">
            <el-option v-for="node in nodes" :key="node.id" :value="node.id" :label="`${NODE_TYPE_LABELS[node.node_type]} · ${node.name}`" />
          </el-select>
        </el-form-item>
        <el-form-item label="终点">
          <el-select v-model="edgeForm.to_node_id" filterable style="width: 100%">
            <el-option v-for="node in nodes" :key="node.id" :value="node.id" :label="`${NODE_TYPE_LABELS[node.node_type]} · ${node.name}`" />
          </el-select>
        </el-form-item>
        <el-form-item label="关系类型">
          <el-select v-model="edgeForm.relation_type" style="width: 100%">
            <el-option v-for="(label, key) in RELATION_LABELS" :key="key" :value="key" :label="label" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="edgeVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEdge">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import type { GraphEdge, GraphNode, NodeTerm, Paginated } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import { LANGS, NODE_TYPE_LABELS, RELATION_LABELS, SOURCE_LABELS } from '../../constants'

const nodeTabs = [
  { type: 'product_line', label: '产品线' },
  { type: 'persona', label: '客户角色' },
  { type: 'market', label: '市场/国家' },
  { type: 'org', label: '机构实体' },
]
const activeTab = ref('product_line')
const nodes = ref<GraphNode[]>([])
const edges = ref<GraphEdge[]>([])
const loading = ref(false)
const loadingEdges = ref(false)

function nodesOf(type: string): GraphNode[] {
  return nodes.value.filter((node) => node.node_type === type)
}
function nodeName(id: number): string {
  return nodes.value.find((node) => node.id === id)?.name ?? `#${id}`
}

async function loadAll() {
  loading.value = true
  loadingEdges.value = true
  try {
    const result = await api.get<Paginated<GraphNode>>('/graph/nodes', { page_size: 500 })
    nodes.value = result.items
    edges.value = await api.get<GraphEdge[]>('/graph/edges')
  } finally {
    loading.value = false
    loadingEdges.value = false
  }
}

// ---- 节点表单 ----
const formVisible = ref(false)
const editingNode = ref<GraphNode | null>(null)
const form = ref({ node_type: 'product_line', name: '', region: '' })

function openCreateDialog() {
  editingNode.value = null
  form.value = { node_type: activeTab.value === 'edges' ? 'product_line' : activeTab.value, name: '', region: '' }
  formVisible.value = true
}
function openEditDialog(row: GraphNode) {
  editingNode.value = row
  form.value = { node_type: row.node_type, name: row.name, region: row.region ?? '' }
  formVisible.value = true
}
async function submitNodeForm() {
  if (!form.value.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  if (editingNode.value) {
    await api.put(`/graph/nodes/${editingNode.value.id}`, {
      name: form.value.name,
      region: form.value.region || null,
    })
  } else {
    await api.post('/graph/nodes', { ...form.value, source: 'manual' })
  }
  ElMessage.success('已保存')
  formVisible.value = false
  await loadAll()
}
async function disableNode(row: GraphNode) {
  await api.del(`/graph/nodes/${row.id}`)
  ElMessage.success('已停用')
  await loadAll()
}
async function reviewNode(row: GraphNode, decision: 'approve' | 'reject') {
  await api.post('/graph/review', { target: 'node', ids: [row.id], decision })
  await loadAll()
}

// ---- 合并 ----
const mergeVisible = ref(false)
const mergeTarget = ref<GraphNode | null>(null)
const mergeSources = ref<number[]>([])
const mergeCandidates = computed(() =>
  nodes.value.filter(
    (node) =>
      mergeTarget.value &&
      node.node_type === mergeTarget.value.node_type &&
      node.id !== mergeTarget.value.id,
  ),
)
function openMergeDialog(row: GraphNode) {
  mergeTarget.value = row
  mergeSources.value = []
  mergeVisible.value = true
}
async function submitMerge() {
  if (!mergeTarget.value || !mergeSources.value.length) {
    ElMessage.warning('请选择要并入的节点')
    return
  }
  const report = await api.post<{ terms_moved: number; edges_moved: number; seeds_moved: number }>(
    '/graph/nodes/merge',
    { target_id: mergeTarget.value.id, source_ids: mergeSources.value },
  )
  ElMessage.success(`已合并：词表 ${report.terms_moved}，关系 ${report.edges_moved}，种子 ${report.seeds_moved}`)
  mergeVisible.value = false
  await loadAll()
}

// ---- 词表 ----
const termsVisible = ref(false)
const termsNode = ref<GraphNode | null>(null)
const terms = ref<NodeTerm[]>([])
const termForm = ref({ lang: 'en', term: '', term_type: 'name' })

async function openTerms(row: GraphNode) {
  termsNode.value = row
  termsVisible.value = true
  terms.value = await api.get<NodeTerm[]>(`/graph/nodes/${row.id}/terms`)
}
async function addTerm() {
  if (!termsNode.value || !termForm.value.term.trim()) {
    ElMessage.warning('请填写词条')
    return
  }
  await api.post(`/graph/nodes/${termsNode.value.id}/terms`, termForm.value)
  termForm.value = { ...termForm.value, term: '' }
  terms.value = await api.get<NodeTerm[]>(`/graph/nodes/${termsNode.value.id}/terms`)
}
async function removeTerm(row: NodeTerm) {
  await api.del(`/graph/terms/${row.id}`)
  if (termsNode.value) {
    terms.value = await api.get<NodeTerm[]>(`/graph/nodes/${termsNode.value.id}/terms`)
  }
}
async function reviewTerm(row: NodeTerm, decision: 'approve' | 'reject') {
  await api.post('/graph/review', { target: 'term', ids: [row.id], decision })
  if (termsNode.value) {
    terms.value = await api.get<NodeTerm[]>(`/graph/nodes/${termsNode.value.id}/terms`)
  }
}

// ---- 关系 ----
const edgeVisible = ref(false)
const edgeForm = ref({ from_node_id: null as number | null, to_node_id: null as number | null, relation_type: 'org_in_market' })
function openEdgeDialog() {
  edgeForm.value = { from_node_id: null, to_node_id: null, relation_type: 'org_in_market' }
  edgeVisible.value = true
}
async function submitEdge() {
  if (!edgeForm.value.from_node_id || !edgeForm.value.to_node_id) {
    ElMessage.warning('请选择起点与终点')
    return
  }
  await api.post('/graph/edges', edgeForm.value)
  ElMessage.success('已创建关系')
  edgeVisible.value = false
  await loadAll()
}
async function removeEdge(row: GraphEdge) {
  await api.del(`/graph/edges/${row.id}`)
  await loadAll()
}

onMounted(loadAll)
</script>

<style scoped>
.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin: 0 0 12px;
}
</style>
