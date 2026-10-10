<template>
  <div>
    <PageHeader
      title="导入与回灌"
      description="种子执行清单导出（供外部执行）、外部收割结果回灌（产量归因）、批量导入种子。"
    />

    <el-row :gutter="16">
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>导出执行清单</template>
          <el-form label-width="90px">
            <el-form-item label="格式">
              <el-radio-group v-model="exportForm.format">
                <el-radio-button value="txt">txt（逐行）</el-radio-button>
                <el-radio-button value="csv">csv（含元数据）</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="批次">
              <el-input v-model="exportForm.batch" placeholder="留空=全部" clearable />
            </el-form-item>
            <el-form-item label="审核范围">
              <el-select v-model="exportForm.review_status">
                <el-option label="仅已采纳" value="approved" />
                <el-option label="含待审核" value="pending" />
              </el-select>
            </el-form-item>
            <el-form-item label="优先级 ≤">
              <el-select v-model="exportForm.max_priority" clearable>
                <el-option label="高（1）" :value="1" />
                <el-option label="中（2）" :value="2" />
                <el-option label="低（3）" :value="3" />
              </el-select>
            </el-form-item>
            <el-form-item label="条数上限">
              <el-input-number v-model="exportForm.limit" :min="1" :max="100000" :step="50" />
            </el-form-item>
          </el-form>
          <el-button type="primary" :loading="exporting" @click="doExport">导出</el-button>
          <div v-if="exportResult" class="result">
            已导出 {{ exportResult.count }} 条 →
            <el-link type="primary" @click="copy(exportResult.path)">{{ exportResult.path }}（点击复制路径）</el-link>
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card shadow="never">
          <template #header>回灌外部收割结果（harvest_v1）</template>
          <el-form label-width="90px">
            <el-form-item label="文件路径">
              <el-input v-model="ingestForm.path" placeholder="本机 jsonl/csv 文件绝对路径（二选一）" />
            </el-form-item>
            <el-form-item label="或粘贴内容">
              <el-input
                v-model="ingestForm.content"
                type="textarea"
                :rows="6"
                placeholder="每行一条：{&quot;saler.schema&quot;:&quot;harvest_v1&quot;,&quot;seed_query&quot;:&quot;…&quot;,&quot;results&quot;:[{&quot;url&quot;:&quot;…&quot;,&quot;title&quot;:&quot;…&quot;}]}"
              />
            </el-form-item>
          </el-form>
          <el-button type="primary" :loading="ingesting" @click="doIngest">回灌</el-button>
          <el-alert
            v-if="ingestReport" type="success" :closable="false" class="result"
            :title="`匹配查询 ${ingestReport.matched} · 新域名 ${ingestReport.new_domains} · 重复 ${ingestReport.dup_domains} · 未匹配 ${(ingestReport.unmatched_queries ?? []).length}`"
          />
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card shadow="never">
          <template #header>批量导入种子</template>
          <p class="hint">每行一条搜索词（也支持粘贴 csv：query,lang,priority,batch,… 带表头）。</p>
          <el-input v-model="importText" type="textarea" :rows="9" placeholder="power fittings supplier kenya&#10;fastener distributor dubai" />
          <el-button type="primary" class="btn" :loading="importing" @click="doImport">导入</el-button>
          <el-alert
            v-if="importReport" type="success" :closable="false"
            :title="`新增 ${importReport.created} · 重复 ${importReport.duplicates.length} · 错误 ${importReport.errors.length}`"
          />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import { watchJob } from '../../api/jobs'
import PageHeader from '../../components/common/PageHeader.vue'

const exportForm = ref({
  format: 'txt',
  batch: '',
  review_status: 'approved',
  max_priority: null as number | null,
  limit: 200,
})
const exportResult = ref<{ path: string; count: number } | null>(null)
const exporting = ref(false)

async function doExport() {
  exporting.value = true
  try {
    exportResult.value = await api.post<{ path: string; count: number }>('/seeds/export', {
      ...exportForm.value,
      batch: exportForm.value.batch || null,
    })
  } finally {
    exporting.value = false
  }
}

const ingestForm = ref({ path: '', content: '' })
const ingestReport = ref<Record<string, any> | null>(null)
const ingesting = ref(false)

async function doIngest() {
  if (!ingestForm.value.path && !ingestForm.value.content.trim()) {
    ElMessage.warning('请填写文件路径或粘贴内容')
    return
  }
  ingesting.value = true
  try {
    const { job_id } = await api.post<{ job_id: number }>('/seeds/ingest', {
      path: ingestForm.value.path || null,
      content: ingestForm.value.content || null,
    })
    const job = await watchJob(job_id)
    if (job.status === 'completed') {
      ingestReport.value = job.result
      ElMessage.success('回灌完成')
    } else {
      ElMessage.error(job.error ?? '回灌失败')
    }
  } finally {
    ingesting.value = false
  }
}

const importText = ref('')
const importReport = ref<{ created: number; duplicates: string[]; errors: unknown[] } | null>(null)
const importing = ref(false)

async function doImport() {
  const lines = importText.value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
  if (!lines.length) {
    ElMessage.warning('请输入种子清单')
    return
  }
  const items: Array<Record<string, unknown>> = []
  for (const line of lines) {
    if (line.toLowerCase().startsWith('query,')) continue // csv 表头
    if (line.includes(',')) {
      const [query, lang, priority, batch] = line.split(',').map((part) => part.trim())
      items.push({
        query,
        lang: lang || 'en',
        priority: priority ? Number(priority) : 2,
        batch: batch || 'import',
      })
    } else {
      items.push({ query: line, batch: 'import' })
    }
  }
  importing.value = true
  try {
    importReport.value = await api.post('/seeds/bulk', { items })
    ElMessage.success(`导入完成：新增 ${importReport.value?.created ?? 0} 条`)
  } finally {
    importing.value = false
  }
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制路径')
  } catch {
    ElMessage.info(text)
  }
}
</script>

<style scoped>
.hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin: 0 0 8px;
}
.btn {
  margin-top: 10px;
}
.result {
  margin-top: 10px;
}
</style>
