<template>
  <div>
    <PageHeader title="客户列表" description="挖掘与导入得到的客户公司：状态推进、标签与合并去重。">
      <template #actions>
        <el-button :disabled="selected.length < 2" @click="openMerge">合并选中（{{ selected.length }}）</el-button>
        <el-button @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <el-card class="filters" shadow="never">
      <el-form inline>
        <el-form-item label="搜索">
          <el-input v-model="filters.q" clearable style="width: 200px" placeholder="公司名 / 域名" @keyup.enter="load" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable style="width: 120px">
            <el-option label="新线索" value="new" />
            <el-option label="已联系" value="contacted" />
            <el-option label="已回复" value="replied" />
            <el-option label="已成交" value="won" />
            <el-option label="未成交" value="lost" />
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
      <el-table v-loading="loading" :data="items" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="42" />
        <el-table-column label="公司" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" @click="openDetail(row as CompanyRow)">{{ row.name || '(未命名)' }}</el-link>
            <el-tag v-if="row.is_excluded" type="danger" size="small" class="chip">已排除</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="domain" label="域名" min-width="170" show-overflow-tooltip />
        <el-table-column label="国家/语言" width="110">
          <template #default="{ row }">{{ row.country || '—' }} / {{ row.language || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="联系方式" width="90">
          <template #default="{ row }">{{ row.contacts_count }}</template>
        </el-table-column>
        <el-table-column label="标签" min-width="140">
          <template #default="{ row }">
            <el-tag v-for="tag in row.tags" :key="tag" size="small" class="chip">{{ tag }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="80" />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openDetail(row as CompanyRow)">详情</el-button>
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

    <el-dialog v-model="mergeVisible" title="合并重复客户（保留目标，其余并入）" width="520px">
      <p class="hint">目标：{{ mergeTarget?.name }}</p>
      <el-select v-model="mergeSources" multiple filterable style="width: 100%" placeholder="选择要并入的客户">
        <el-option
          v-for="item in mergeCandidates"
          :key="item.id"
          :value="item.id"
          :label="`${item.name}（${item.domain || item.id}）`"
        />
      </el-select>
      <template #footer>
        <el-button @click="mergeVisible = false">取消</el-button>
        <el-button type="primary" @click="submitMerge">合并</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import type { CompanyRow, Paginated } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import StatusTag from '../../components/common/StatusTag.vue'

const router = useRouter()
const items = ref<CompanyRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)
const selected = ref<CompanyRow[]>([])
const filters = ref({ q: '', status: '', excluded: null as boolean | null })

const mergeVisible = ref(false)
const mergeTarget = ref<CompanyRow | null>(null)
const mergeSources = ref<number[]>([])
const mergeCandidates = computed(() =>
  selected.value.filter((item) => item.id !== mergeTarget.value?.id),
)

function onSelectionChange(rows: CompanyRow[]) {
  selected.value = rows
}

async function load() {
  loading.value = true
  try {
    const result = await api.get<Paginated<CompanyRow>>('/companies', {
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

function openDetail(row: CompanyRow) {
  router.push(`/leads/companies/${row.id}`)
}

function openMerge() {
  mergeTarget.value = selected.value[0]
  mergeSources.value = []
  mergeVisible.value = true
}

async function submitMerge() {
  if (!mergeTarget.value || !mergeSources.value.length) {
    ElMessage.warning('请选择要并入的客户')
    return
  }
  const report = await api.post<{ domains_moved: number; contacts_moved: number }>(
    '/companies/merge',
    { target_id: mergeTarget.value.id, source_ids: mergeSources.value },
  )
  ElMessage.success(`已合并：域名 ${report.domains_moved}，联系方式 ${report.contacts_moved}`)
  mergeVisible.value = false
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
.chip {
  margin-left: 6px;
}
.hint {
  color: var(--el-text-color-secondary);
  margin: 0 0 10px;
}
</style>
