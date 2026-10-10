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
        <el-input v-model="batch" placeholder="批次筛选（可选）" clearable style="width: 170px" />
        <el-button type="primary" @click="load">加载</el-button>
      </template>
    </PageHeader>

    <el-card shadow="never">
      <div class="legend">
        <span><i class="dot" style="background: #67c23a" /> 已产出联系方式</span>
        <span><i class="dot" style="background: #e6a23c" /> 已执行·无联系方式</span>
        <span><i class="dot" style="background: #409eff" /> 已建种子·待执行</span>
        <span><i class="dot" style="background: #c0c4cc" /> 空白（无种子）</span>
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
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { api } from '../../api/client'
import type { OverviewPayload, OverviewNode } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import { NODE_TYPE_LABELS } from '../../constants'

const STRUCTURE_TYPES = ['product_line', 'persona', 'market']
const ENTITY_TYPES = ['org', 'market']

const viewMode = ref<'structure' | 'entity'>('structure')
const batch = ref('')
const loading = ref(false)
const chartEl = ref<HTMLDivElement>()
const activeNode = ref<OverviewNode | null>(null)
const router = useRouter()
let chart: echarts.ECharts | null = null
let payload: OverviewPayload = { nodes: [], edges: [] }

function colorOf(node: OverviewNode): string {
  if (node.counts.contacts > 0) return '#67c23a'
  if (node.counts.done > 0) return '#e6a23c'
  if (node.counts.seeds > 0) return '#409eff'
  return '#c0c4cc'
}

async function load() {
  loading.value = true
  try {
    payload = await api.get<OverviewPayload>('/graph/overview', {
      batch: batch.value || undefined,
    })
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
        activeNode.value = payload.nodes.find((node) => node.id === id) ?? null
      }
    })
  }
  const allowed = new Set(viewMode.value === 'structure' ? STRUCTURE_TYPES : ENTITY_TYPES)
  const nodes = payload.nodes.filter((node) => allowed.has(node.node_type))
  const included = new Set(nodes.map((node) => node.id))
  const links = payload.edges.filter((edge) => included.has(edge.source) && included.has(edge.target))

  const categories = [...allowed].map((type) => ({ name: NODE_TYPE_LABELS[type] ?? type }))
  const categoryIndex = (type: string) => categories.findIndex((c) => c.name === (NODE_TYPE_LABELS[type] ?? type))

  chart.setOption(
    {
      tooltip: {
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
          label: { show: true, position: 'right', fontSize: 11 },
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
              color: edge.relation_type === 'seed_cooccur' ? '#b1b3b8' : '#7a7d85',
              type: edge.relation_type === 'seed_cooccur' ? 'solid' : 'dashed',
            },
          })),
        },
      ],
    },
    true,
  )
}

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
  await load()
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
