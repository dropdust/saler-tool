<template>
  <div>
    <PageHeader title="产量统计" description="哪个批次/产品线/角色/市场在产出；识别零产出种子以淘汰。">
      <template #actions>
        <el-select v-model="groupBy" style="width: 130px" @change="load">
          <el-option label="按批次" value="batch" />
          <el-option label="按产品线" value="product_line" />
          <el-option label="按客户角色" value="persona" />
          <el-option label="按市场" value="market" />
        </el-select>
        <el-button @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <el-row :gutter="16" class="cards">
      <el-col :span="6"><el-card shadow="never"><div class="stat"><div class="num">{{ totals.seeds }}</div><div class="meta">种子总数</div></div></el-card></el-col>
      <el-col :span="6"><el-card shadow="never"><div class="stat"><div class="num">{{ totals.done }}</div><div class="meta">已执行</div></div></el-card></el-col>
      <el-col :span="6"><el-card shadow="never"><div class="stat"><div class="num">{{ totals.candidates }}</div><div class="meta">候选公司（按条归因，含重复）</div></div></el-card></el-col>
      <el-col :span="6"><el-card shadow="never"><div class="stat"><div class="num">{{ totals.contacts }}</div><div class="meta">联系方式（按条归因，含重复）</div></div></el-card></el-col>
    </el-row>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="rows">
        <el-table-column prop="name" label="分组" min-width="200" show-overflow-tooltip />
        <el-table-column prop="seeds" label="种子" width="90" sortable />
        <el-table-column prop="done" label="已执行" width="90" sortable />
        <el-table-column prop="candidates" label="候选公司" width="110" sortable />
        <el-table-column prop="contacts" label="联系方式" width="110" sortable />
        <el-table-column label="产出密度" min-width="180">
          <template #default="{ row }">
            <el-progress :percentage="density(row as StatsRow)" :stroke-width="10" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="zero-card">
      <template #header>零产出种子（已执行但无联系方式，建议复核翻译或淘汰）</template>
      <el-table v-loading="loadingZero" :data="zeroYield">
        <el-table-column prop="query" label="搜索词" min-width="260" show-overflow-tooltip />
        <el-table-column prop="batch" label="批次" width="150" />
        <el-table-column label="语言" width="80">
          <template #default="{ row }">{{ langLabel(row.lang) }}</template>
        </el-table-column>
        <el-table-column prop="n_candidates" label="候选公司" width="100" />
        <el-table-column prop="n_contacts" label="联系方式" width="100" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api/client'
import type { Paginated, Seed, StatsRow } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import { langLabel } from '../../constants'

const groupBy = ref('batch')
const rows = ref<StatsRow[]>([])
const loading = ref(false)
const zeroYield = ref<Seed[]>([])
const loadingZero = ref(false)

const totals = computed(() => {
  const sum = { seeds: 0, done: 0, candidates: 0, contacts: 0 }
  for (const row of rows.value) {
    sum.seeds += row.seeds
    sum.done += row.done
    sum.candidates += row.candidates
    sum.contacts += row.contacts
  }
  return sum
})

function density(row: StatsRow): number {
  const max = Math.max(...rows.value.map((item) => item.contacts), 1)
  return Math.round((row.contacts / max) * 100)
}

async function load() {
  loading.value = true
  try {
    rows.value = await api.get<StatsRow[]>('/seeds/stats', { group_by: groupBy.value })
  } finally {
    loading.value = false
  }
}

async function loadZeroYield() {
  loadingZero.value = true
  try {
    const result = await api.get<Paginated<Seed>>('/seeds', {
      status: 'done',
      review_status: '',
      sort: 'yield',
      page: 1,
      page_size: 200,
    })
    zeroYield.value = result.items.filter((seed) => seed.n_contacts === 0).slice(0, 50)
  } finally {
    loadingZero.value = false
  }
}

onMounted(async () => {
  await Promise.all([load(), loadZeroYield()])
})
</script>

<style scoped>
.cards {
  margin-bottom: 12px;
}
.stat .num {
  font-size: 26px;
  font-weight: 600;
}
.stat .meta {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-top: 4px;
}
.zero-card {
  margin-top: 12px;
}
</style>
