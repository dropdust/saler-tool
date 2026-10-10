<template>
  <div>
    <PageHeader
      title="排除规则"
      description="过滤同行/供应商/无关站点：命中对象移出买家列表单独存放（不删除），后续营销人群自动排除。"
    >
      <template #actions>
        <el-button type="primary" @click="openCreate">新建规则</el-button>
        <el-button type="warning" :loading="applying" @click="applyRules">对存量重跑</el-button>
        <el-button @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="items">
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ RULE_TYPE_LABELS[row.rule_type] || row.rule_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="内容" min-width="320">
          <template #default="{ row }">
            <pre class="pattern">{{ row.pattern }}</pre>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-switch
              :model-value="row.enabled"
              @change="(value: string | number | boolean) => toggle(row as ExclusionRuleRow, Boolean(value))"
            />
          </template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="danger" @click="remove(row as ExclusionRuleRow)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-alert
        class="tip"
        type="info"
        :closable="false"
        show-icon
        title="关键词：匹配标题/摘要/域名；域名：精确或子域匹配；名单：每行一条（关键词或域名混合）。"
      />
    </el-card>

    <el-dialog v-model="createVisible" title="新建排除规则" width="520px">
      <el-form label-width="90px">
        <el-form-item label="类型">
          <el-radio-group v-model="form.rule_type">
            <el-radio-button value="keyword">关键词</el-radio-button>
            <el-radio-button value="domain">域名</el-radio-button>
            <el-radio-button value="list">名单</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="内容">
          <el-input
            v-model="form.pattern"
            :type="form.rule_type === 'list' ? 'textarea' : 'text'"
            :rows="5"
            :placeholder="form.rule_type === 'list' ? '每行一条（关键词或域名）' : form.rule_type === 'domain' ? '如 competitor.com' : '如 wholesale directory'"
          />
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="form.note" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import type { ExclusionRuleRow } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'

const RULE_TYPE_LABELS: Record<string, string> = {
  keyword: '关键词',
  domain: '域名',
  list: '名单',
}

const items = ref<ExclusionRuleRow[]>([])
const loading = ref(false)
const applying = ref(false)
const createVisible = ref(false)
const form = ref({ rule_type: 'keyword', pattern: '', note: '', enabled: true })

async function load() {
  loading.value = true
  try {
    items.value = await api.get<ExclusionRuleRow[]>('/exclusion-rules')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.value = { rule_type: 'keyword', pattern: '', note: '', enabled: true }
  createVisible.value = true
}

async function submit() {
  if (!form.value.pattern.trim()) {
    ElMessage.warning('请填写规则内容')
    return
  }
  await api.post('/exclusion-rules', form.value)
  ElMessage.success('已创建')
  createVisible.value = false
  await load()
}

async function toggle(row: ExclusionRuleRow, value: boolean) {
  await api.put(`/exclusion-rules/${row.id}`, { enabled: value })
  await load()
}

async function remove(row: ExclusionRuleRow) {
  await api.del(`/exclusion-rules/${row.id}`)
  await load()
}

async function applyRules() {
  applying.value = true
  try {
    const report = await api.post<{ evaluated: number; excluded: number }>('/exclusion-rules/apply')
    ElMessage.success(`已评估 ${report.evaluated} 个域名，新排除 ${report.excluded} 个`)
    await load()
  } finally {
    applying.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.pattern {
  margin: 0;
  white-space: pre-wrap;
  font-family: monospace;
  font-size: 12px;
}
.tip {
  margin-top: 12px;
}
</style>
