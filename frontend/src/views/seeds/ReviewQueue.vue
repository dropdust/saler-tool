<template>
  <div>
    <PageHeader
      title="待审核"
      description="大模型/检索来源的候选种子：采纳后方可进入执行队列（先审后发）。"
    >
      <template #actions>
        <el-button @click="load">刷新</el-button>
        <el-button type="success" :disabled="!selected.length" @click="reviewSelected('approve')">
          采纳选中（{{ selected.length }}）
        </el-button>
        <el-button type="danger" :disabled="!selected.length" @click="reviewSelected('reject')">
          拒绝选中
        </el-button>
        <el-button type="primary" plain :disabled="!items.length" @click="approveAll">
          采纳本页全部
        </el-button>
      </template>
    </PageHeader>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="items" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="42" />
        <el-table-column prop="query" label="搜索词" min-width="260" show-overflow-tooltip />
        <el-table-column label="语言" width="70">
          <template #default="{ row }">{{ row.lang }}</template>
        </el-table-column>
        <el-table-column label="来源" width="80">
          <template #default="{ row }">{{ SOURCE_LABELS[row.source] ?? row.source }}</template>
        </el-table-column>
        <el-table-column prop="batch" label="批次" width="150" />
        <el-table-column label="置信度" width="90">
          <template #default="{ row }">{{ row.confidence ?? '—' }}</template>
        </el-table-column>
        <el-table-column prop="note" label="生成说明" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="success" text @click="reviewOne(row as Seed, 'approve')">采纳</el-button>
            <el-button size="small" type="danger" text @click="reviewOne(row as Seed, 'reject')">拒绝</el-button>
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import type { Paginated, Seed } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import { SOURCE_LABELS } from '../../constants'

const items = ref<Seed[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const selected = ref<Seed[]>([])

function onSelectionChange(rows: Seed[]) {
  selected.value = rows
}

async function load() {
  loading.value = true
  try {
    const result = await api.get<Paginated<Seed>>('/seeds/review-queue', {
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

async function reviewSelected(decision: 'approve' | 'reject') {
  await api.post('/seeds/review', { ids: selected.value.map((row) => row.id), decision })
  ElMessage.success(decision === 'approve' ? '已采纳' : '已拒绝')
  await load()
}

async function reviewOne(row: Seed, decision: 'approve' | 'reject') {
  await api.post('/seeds/review', { ids: [row.id], decision })
  await load()
}

async function approveAll() {
  await api.post('/seeds/review', { ids: items.value.map((row) => row.id), decision: 'approve' })
  ElMessage.success('已采纳本页全部')
  await load()
}

onMounted(load)
</script>

<style scoped>
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
