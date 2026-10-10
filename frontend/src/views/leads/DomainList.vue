<template>
  <div>
    <PageHeader title="候选域名" description="挖掘发现的候选公司域名：抓取状态、国家/语言与排除管理。">
      <template #actions>
        <el-button @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <el-card class="filters" shadow="never">
      <el-form inline>
        <el-form-item label="域名">
          <el-input v-model="filters.q" clearable style="width: 180px" @keyup.enter="load" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable style="width: 140px">
            <el-option label="待抓取" value="pending" />
            <el-option label="已抓取" value="done" />
            <el-option label="无联系方式" value="no_contact" />
            <el-option label="失败" value="failed" />
          </el-select>
        </el-form-item>
        <el-form-item label="排除">
          <el-select v-model="filters.excluded" clearable style="width: 110px">
            <el-option label="正常" :value="false" />
            <el-option label="已排除" :value="true" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="items">
        <el-table-column label="域名" min-width="210" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link
              v-if="row.homepage_url"
              :href="(row as DomainRow).homepage_url ?? undefined"
              target="_blank"
              type="primary"
            >
              {{ row.domain }}
            </el-link>
            <span v-else>{{ row.domain }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="190" show-overflow-tooltip />
        <el-table-column label="状态" width="110">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="国家" width="70">
          <template #default="{ row }">{{ row.country || '—' }}</template>
        </el-table-column>
        <el-table-column label="语言" width="70">
          <template #default="{ row }">{{ row.language || '—' }}</template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="100" />
        <el-table-column label="页/次" width="90">
          <template #default="{ row }">{{ row.fetched_pages }} / {{ row.attempts }}</template>
        </el-table-column>
        <el-table-column label="排除" width="180" fixed="right">
          <template #default="{ row }">
            <el-tag v-if="row.is_excluded" type="danger" size="small">
              {{ row.exclusion_reason || '已排除' }}
            </el-tag>
            <el-button
              size="small"
              text
              :type="row.is_excluded ? 'success' : 'danger'"
              @click="toggleExclude(row as DomainRow)"
            >
              {{ row.is_excluded ? '恢复' : '排除' }}
            </el-button>
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
import type { DomainRow, Paginated } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import StatusTag from '../../components/common/StatusTag.vue'

const items = ref<DomainRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)
const filters = ref({
  q: '',
  status: '',
  excluded: null as boolean | null,
})

async function load() {
  loading.value = true
  try {
    const result = await api.get<Paginated<DomainRow>>('/domains', {
      q: filters.value.q,
      status: filters.value.status,
      excluded: filters.value.excluded,
      page: page.value,
      page_size: pageSize,
    })
    items.value = result.items
    total.value = result.total
  } finally {
    loading.value = false
  }
}

async function toggleExclude(row: DomainRow) {
  const next = !row.is_excluded
  await api.put(`/domains/${row.id}`, {
    is_excluded: next,
    exclusion_reason: next ? 'manual' : '',
  })
  ElMessage.success(next ? '已移出买家列表（单独存放）' : '已恢复')
  await load()
}

onMounted(load)
</script>

<style scoped>
.filters {
  margin-bottom: 12px;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
