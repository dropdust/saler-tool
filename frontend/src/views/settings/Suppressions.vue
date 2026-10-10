<template>
  <div>
    <PageHeader
      title="退订 / 黑名单"
      description="命中对象在所有后续营销计划中自动排除（FR-051）；发送前二次校验，即时生效。"
    >
      <template #actions>
        <el-button type="primary" @click="openCreate">添加条目</el-button>
        <el-button @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <el-card shadow="never">
      <div class="filters">
        <el-select v-model="scopeFilter" clearable placeholder="范围筛选" style="width: 160px" @change="load">
          <el-option v-for="(label, key) in SCOPE_LABELS" :key="key" :value="key" :label="label" />
        </el-select>
        <span class="muted">邮箱/域名不区分大小写；加入退订后无需重跑计划——发送前的校验会自动拦截。</span>
      </div>
      <el-table v-loading="loading" :data="items">
        <el-table-column label="范围" width="110">
          <template #default="{ row }">{{ SCOPE_LABELS[row.scope] || row.scope }}</template>
        </el-table-column>
        <el-table-column prop="target_value" label="对象值" min-width="220" show-overflow-tooltip />
        <el-table-column label="原因" width="110">
          <template #default="{ row }">{{ REASON_LABELS[row.reason] || row.reason }}</template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="160" show-overflow-tooltip />
        <el-table-column label="加入时间" width="160">
          <template #default="{ row }">{{ (row.created_at || '').slice(0, 19).replace('T', ' ') }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="danger" @click="remove(row as SuppressionRow)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <EmptyState
        v-if="!loading && !items.length"
        description="暂无退订/黑名单条目：客户要求退订时在此登记，全部计划将自动排除"
      />
    </el-card>

    <el-dialog v-model="createVisible" title="添加退订/黑名单" width="520px">
      <el-form label-width="100px">
        <el-form-item label="范围">
          <el-radio-group v-model="form.scope">
            <el-radio-button value="email">邮箱</el-radio-button>
            <el-radio-button value="phone">电话</el-radio-button>
            <el-radio-button value="domain">域名</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="form.scope === 'domain' ? '域名' : form.scope === 'phone' ? '电话' : '邮箱'" required>
          <el-input v-model="form.target_value" :placeholder="SCOPE_HINTS[form.scope]" />
        </el-form-item>
        <el-form-item label="原因">
          <el-select v-model="form.reason" style="width: 100%">
            <el-option v-for="(label, key) in REASON_LABELS" :key="key" :value="key" :label="label" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="2" placeholder="如：2026-10-11 邮件回复「请勿再联系」" />
        </el-form-item>
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          title="加入后：该对象将从所有后续计划的人群中排除；进行中的计划在下一次发送前自动跳过。"
        />
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="submitCreate">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import type { SuppressionRow } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import EmptyState from '../../components/common/EmptyState.vue'

const SCOPE_LABELS: Record<string, string> = {
  email: '邮箱',
  phone: '电话',
  contact: '联系方式',
  company: '客户',
  domain: '域名',
}
const REASON_LABELS: Record<string, string> = {
  unsubscribed: '主动退订',
  bounced: '退信',
  complaint: '投诉',
  manual: '手动加入',
  invalid: '无效地址',
}
const SCOPE_HINTS: Record<string, string> = {
  email: 'someone@example.com',
  phone: '+8613800000000',
  domain: 'example.com',
  contact: '',
  company: '',
}

const items = ref<SuppressionRow[]>([])
const loading = ref(false)
const scopeFilter = ref('')
const createVisible = ref(false)
const form = ref({ scope: 'email', target_value: '', reason: 'unsubscribed', note: '' })

async function load() {
  loading.value = true
  try {
    items.value = await api.get<SuppressionRow[]>('/suppressions', {
      scope: scopeFilter.value || undefined,
    })
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.value = { scope: 'email', target_value: '', reason: 'unsubscribed', note: '' }
  createVisible.value = true
}

async function submitCreate() {
  if (!form.value.target_value.trim()) {
    ElMessage.warning('请填写对象值')
    return
  }
  const result = await api.post<{ created: boolean }>('/suppressions', {
    ...form.value,
    source: 'manual',
  })
  ElMessage.success(result.created ? '已加入黑名单' : '已存在（未重复添加）')
  createVisible.value = false
  await load()
}

async function remove(row: SuppressionRow) {
  await api.del(`/suppressions/${row.id}`)
  ElMessage.success('已移除（该对象将重新进入后续人群）')
  await load()
}

onMounted(load)
</script>

<style scoped>
.filters {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
