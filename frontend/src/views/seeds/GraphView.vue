<template>
  <div>
    <PageHeader
      title="图谱视图"
      description="结构视图（产品线-客户角色-市场）与实体视图（机构-市场）；颜色/大小反映产量，识别空白市场。"
    >
      <template #actions>
        <el-radio-group v-model="viewMode" @change="renderChart">
          <el-radio-button value="structure">结构视图</el-radio-button>
          <el-radio-button value="entity">实体视图</el-radio-button>
        </el-radio-group>
        <el-select
          v-model="batch"
          data-test="batch-filter"
          placeholder="批次筛选（可选）"
          clearable
          filterable
          allow-create
          default-first-option
          style="width: 180px"
        >
          <el-option v-for="item in batchOptions" :key="item" :label="item" :value="item" />
        </el-select>
        <el-autocomplete
          v-model="searchText"
          data-test="node-search"
          placeholder="搜索节点并定位"
          clearable
          :debounce="0"
          value-key="label"
          :fetch-suggestions="fetchNodeSuggestions"
          style="width: 200px"
          @select="onNodeSelect"
          @clear="onSearchClear"
        >
          <template #default="{ item }">
            <span>{{ item.label }}</span>
          </template>
        </el-autocomplete>
        <el-button type="primary" @click="load">加载</el-button>
      </template>
    </PageHeader>

    <el-card shadow="never">
      <div class="legend">
        <span><i class="dot dot-success" /> 已产出联系方式</span>
        <span><i class="dot dot-warning" /> 已执行·无联系方式</span>
        <span><i class="dot dot-primary" /> 已建种子·待执行</span>
        <span><i class="dot dot-info" /> 空白（无种子）</span>
        <span class="tip">节点大小 = 种子数/产量；拖拽可调整布局，滚轮缩放</span>
      </div>
      <div ref="chartEl" v-loading="loading" class="chart" />

      <el-card v-if="activeNode" shadow="never" class="node-panel">
        <template #header>
          <b>{{ activeNode.name }}</b>
          <el-tag size="small" class="tag">{{ NODE_TYPE_LABELS[activeNode.node_type] ?? activeNode.node_type }}</el-tag>
          <el-tag v-if="activeNode.region" size="small" type="info" class="tag">{{ activeNode.region }}</el-tag>
        </template>
        <p>
          种子 {{ activeNode.counts.seeds }} 条（已完成 {{ activeNode.counts.done }}）·
          候选公司 {{ activeNode.counts.candidates }} · 联系方式 {{ activeNode.counts.contacts }}
        </p>
        <el-button size="small" @click="goSeeds(activeNode)">查看该节点种子</el-button>
      </el-card>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { api } from '../../api/client'
import type { OverviewNode, OverviewPayload } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import { NODE_TYPE_LABELS } from '../../constants'
import { useThemeStore } from '../../stores/theme'
import { nodeColor, readThemePalette } from '../../theme/palette'
import { nodeSearchSuggestions, type NodeSuggestion } from './graphSearch'

const themeStore = useThemeStore()

const STRUCTURE_TYPES = ['product_line', 'persona', 'market']
const ENTITY_TYPES = ['org', 'market']
const STRUCTURE_SET = new Set<string>(STRUCTURE_TYPES)
const ENTITY_SET = new Set<string>(ENTITY_TYPES)

const viewMode = ref<'structure' | 'entity'>('structure')
const batch = ref('')
const batchOptions = ref<string[]>([])
const searchText = ref('')
const loading = ref(false)
const chartEl = ref<HTMLDivElement>()
const activeNode = ref<OverviewNode | null>(null)
const router = useRouter()
let chart: echarts.ECharts | null = null
const payload = ref<OverviewPayload>({ nodes: [], edges: [] })
let renderedNodes: OverviewNode[] = []

function allowedTypes(): Set<string> {
  return viewMode.value === 'structure' ? STRUCTURE_SET : ENTITY_SET
}

function colorOf(node: OverviewNode): string {
  return nodeColor(node.counts, readThemePalette())
}

async function loadBatchOptions() {
  try {
    const items = await api.get<string[]>('/seeds/batches')
    batchOptions.value = Array.isArray(items) ? items : []
  } catch {
    // 选项拉取失败不阻断图加载：下拉为空，仍可用 allow-create 手输批次（少见）
    batchOptions.value = []
  }
}

async function load() {
  loading.value = true
  try {
    payload.value = await api.get<OverviewPayload>('/graph/overview', {
      batch: batch.value || undefined,
    })
    // 批次过滤后搜索目标可能已不在图内：清理选中与面板，避免展示陈旧节点
    const activeId = activeNode.value?.id
    if (activeId != null && !payload.value.nodes.some((node) => node.id === activeId)) {
      activeNode.value = null
      searchText.value = ''
    }
    renderChart()
  } finally {
    loading.value = false
  }
}

function renderChart() {
  if (!chartEl.value) return
  if (!chart) {
    chart = echarts.init(chartEl.value)
    chart.on('click', (params: Record<string, any>) => {
      if (params.dataType === 'node' && params.data?.id) {
        const id = Number(params.data.id)
        activeNode.value = payload.value.nodes.find((node) => node.id === id) ?? null
      }
    })
  }
  const allowed = allowedTypes()
  const nodes = payload.value.nodes.filter((node) => allowed.has(node.node_type))
  renderedNodes = nodes
  const included = new Set(nodes.map((node) => node.id))
  const links = payload.value.edges.filter((edge) => included.has(edge.source) && included.has(edge.target))

  const categories = [...allowed].map((type) => ({ name: NODE_TYPE_LABELS[type] ?? type }))
  const categoryIndex = (type: string) => categories.findIndex((c) => c.name === (NODE_TYPE_LABELS[type] ?? type))
  const palette = readThemePalette()

  chart.setOption(
    {
      tooltip: {
        backgroundColor: palette.tooltipBg,
        borderColor: palette.tooltipBorder,
        textStyle: { color: palette.tooltipText },
        formatter: (params: { dataType?: string; data?: { name?: string; counts?: { seeds: number; done: number; candidates: number; contacts: number } } }) => {
          if (params.dataType === 'edge') return ''
          const counts = params.data?.counts
          if (!counts) return params.data?.name ?? ''
          return (
            `<b>${params.data?.name}</b><br/>种子 ${counts.seeds}（完成 ${counts.done}）<br/>` +
            `候选公司 ${counts.candidates} · 联系方式 ${counts.contacts}`
          )
        },
      },
      series: [
        {
          type: 'graph',
          layout: 'force',
          roam: true,
          draggable: true,
          label: { show: true, position: 'right', fontSize: 11, color: palette.textPrimary },
          force: { repulsion: 300, edgeLength: [70, 170], gravity: 0.06 },
          emphasis: { focus: 'adjacency', label: { fontSize: 13 } },
          categories,
          data: nodes.map((node) => ({
            id: String(node.id),
            name: node.name,
            category: categoryIndex(node.node_type),
            symbolSize: Math.min(60, 12 + node.counts.seeds * 2.5 + node.counts.contacts * 1.5),
            itemStyle: { color: colorOf(node) },
            counts: node.counts,
          })),
          links: links.map((edge) => ({
            source: String(edge.source),
            target: String(edge.target),
            lineStyle: {
              width: Math.min(6, 1 + edge.weight),
              color: edge.relation_type === 'seed_cooccur' ? palette.edgeSolid : palette.edgeDashed,
              type: edge.relation_type === 'seed_cooccur' ? 'solid' : 'dashed',
            },
          })),
        },
      ],
    },
    true,
  )
}

function fetchNodeSuggestions(query: string, callback: (items: NodeSuggestion[]) => void) {
  callback(nodeSearchSuggestions(payload.value.nodes, query))
}

// el-autocomplete 的 select 回调参数为宽松 Record（Element Plus 类型口径），此处收窄为建议项
function onNodeSelect(item: Record<string, unknown>) {
  const id = typeof item.id === 'number' ? item.id : null
  const node = id == null ? null : payload.value.nodes.find((candidate) => candidate.id === id) ?? null
  activeNode.value = node
  if (!node) return
  if (!allowedTypes().has(node.node_type)) {
    // 命中另一视图的节点：自动切换到包含它的视图后定位（market 两视图共有，不切换）
    viewMode.value = STRUCTURE_SET.has(node.node_type) ? 'structure' : 'entity'
    renderChart()
  }
  locateNode(node.id)
}

function onSearchClear() {
  activeNode.value = null
}

/** 定位票据：新一次定位使旧的按帧重试/校正回调失效。 */
let locateTicket = 0

/** 搜索定位（T198）：高亮命中节点（邻接聚焦随 emphasis 生效）+ 提示框 + 平移到视口中央。 */
function locateNode(id: number) {
  const dataIndex = renderedNodes.findIndex((node) => node.id === id)
  if (!chart || dataIndex < 0) return
  chart.dispatchAction({ type: 'downplay', seriesIndex: 0 })
  chart.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex })
  chart.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex })
  centerOnNode(dataIndex, ++locateTicket)
}

interface GraphModelLike {
  getSeriesByIndex?: (index: number) => {
    getData: () => { getItemLayout: (index: number) => number[] | undefined }
    coordinateSystem?: { dataToPoint?: (value: number[]) => number[] }
  } | undefined
}

/**
 * 把节点平移到视口中央：力导向布局逐帧生成，坐标未就绪时按帧重试；
 * 就位后隔 400ms 校正两次，抵消布局继续收敛带来的漂移。
 */
function centerOnNode(dataIndex: number, ticket: number, retries = 0, corrections = 2) {
  if (!chart || ticket !== locateTicket || retries > 30) return
  const model = (chart as unknown as { getModel?: () => GraphModelLike }).getModel?.()
  const seriesModel = model?.getSeriesByIndex?.(0)
  const layout = seriesModel?.getData().getItemLayout(dataIndex)
  const point = layout && seriesModel?.coordinateSystem?.dataToPoint?.(layout)
  if (!point || !Number.isFinite(point[0]) || !Number.isFinite(point[1])) {
    window.requestAnimationFrame(() => centerOnNode(dataIndex, ticket, retries + 1, corrections))
    return
  }
  chart.dispatchAction({
    type: 'graphRoam',
    seriesIndex: 0,
    dx: chart.getWidth() / 2 - point[0],
    dy: chart.getHeight() / 2 - point[1],
  })
  if (corrections > 0) {
    window.setTimeout(() => centerOnNode(dataIndex, ticket, 0, corrections - 1), 400)
  }
}

// 主题切换 → 整图重渲（canvas 不随 CSS 变量自动更新，R5）
watch(
  () => themeStore.current,
  () => renderChart(),
)

function goSeeds(node: OverviewNode) {
  if (node.node_type === 'market') {
    router.push({ path: '/seeds', query: { market_id: String(node.id) } })
  } else {
    router.push('/seeds')
  }
}

function onResize() {
  chart?.resize()
}

onMounted(async () => {
  window.addEventListener('resize', onResize)
  await Promise.all([loadBatchOptions(), load()])
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.chart {
  height: 560px;
  width: 100%;
}
.legend {
  display: flex;
  gap: 18px;
  align-items: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 4px;
}
/* 图例语义色：随主题变量切换（FR-008；禁止硬编码） */
.dot-success {
  background: var(--el-color-success);
}
.dot-warning {
  background: var(--el-color-warning);
}
.dot-primary {
  background: var(--el-color-primary);
}
.dot-info {
  background: var(--el-color-info);
}
.tip {
  margin-left: auto;
}
.node-panel {
  margin-top: 12px;
}
.tag {
  margin-left: 8px;
}
</style>
