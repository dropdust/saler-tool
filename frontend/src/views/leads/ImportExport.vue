<template>
  <div>
    <PageHeader title="导入与导出" description="导入既有客户名单（CSV/XLSX）；导出买家列表（可含被排除与统计）。" />
    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>导入客户名单</template>
          <p class="hint">
            支持中英文表头（邮箱/电话/公司/域名/国家/使用语言/标签/备注）；匹配键先域名后邮箱；
            退订黑名单自动联动并标记无效。
          </p>
          <el-form label-width="90px">
            <el-form-item label="文件路径">
              <el-input v-model="importPath" placeholder="本机 .csv / .xlsx 绝对路径（二选一）" />
            </el-form-item>
            <el-form-item label="或粘贴 CSV">
              <el-input
                v-model="importContent"
                type="textarea"
                :rows="7"
                placeholder="email,phone,company_name,domain,country,language,tags,note"
              />
            </el-form-item>
          </el-form>
          <el-button type="primary" :loading="importing" @click="doImport">开始导入</el-button>
          <el-descriptions v-if="importReport" :column="2" border class="result">
            <el-descriptions-item label="新增公司">{{ importReport.new_companies }}</el-descriptions-item>
            <el-descriptions-item label="并入已有">{{ importReport.merged_companies }}</el-descriptions-item>
            <el-descriptions-item label="新增联系方式">{{ importReport.new_contacts }}</el-descriptions-item>
            <el-descriptions-item label="重复跳过">{{ importReport.dup_contacts }}</el-descriptions-item>
            <el-descriptions-item label="黑名单命中">{{ importReport.suppressed }}</el-descriptions-item>
            <el-descriptions-item label="错误行">{{ importReport.errors?.length ?? 0 }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never">
          <template #header>导出买家列表</template>
          <el-form label-width="90px">
            <el-form-item label="格式">
              <el-radio-group v-model="exportForm.format">
                <el-radio-button value="csv">CSV</el-radio-button>
                <el-radio-button value="xlsx">Excel（含被排除/统计）</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="状态筛选">
              <el-select v-model="exportForm.status" clearable style="width: 160px">
                <el-option label="新线索" value="new" />
                <el-option label="已联系" value="contacted" />
                <el-option label="已回复" value="replied" />
              </el-select>
            </el-form-item>
            <el-form-item label="国家">
              <el-input v-model="exportForm.country" style="width: 120px" placeholder="如 ke" />
            </el-form-item>
          </el-form>
          <el-button type="primary" :loading="exporting" @click="doExport">导出</el-button>
          <div v-if="exportResult" class="result">
            <p>共 {{ exportResult.rows }} 行（被排除 {{ exportResult.excluded }} 家单独列出）</p>
            <el-link type="primary" @click="copy(exportResult.path)">{{ exportResult.path }}（点击复制路径）</el-link>
          </div>
          <el-alert
            class="result"
            type="info"
            :closable="false"
            show-icon
            title="被排除对象（同行/供应商/无关站点）不进买家主表；Excel 版另含「被排除」「统计」Sheet。"
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
import { useJobCenterStore } from '../../stores/jobCenter'
import PageHeader from '../../components/common/PageHeader.vue'

const importPath = ref('')
const jobCenter = useJobCenterStore()
const importContent = ref('')
const importReport = ref<Record<string, any> | null>(null)
const importing = ref(false)

async function doImport() {
  if (!importPath.value.trim() && !importContent.value.trim()) {
    ElMessage.warning('请填写文件路径或粘贴 CSV')
    return
  }
  importing.value = true
  try {
    const { job_id } = await api.post<{ job_id: number }>('/companies/import', {
      path: importPath.value.trim() || null,
      content: importContent.value || null,
    })
    const job = await jobCenter.waitFor(job_id)
    if (job.status === 'completed') {
      importReport.value = job.result
      ElMessage.success('导入完成')
    } else {
      ElMessage.error(job.error ?? '导入失败')
    }
  } finally {
    importing.value = false
  }
}

const exportForm = ref({ format: 'csv', status: '', country: '' })
const exportResult = ref<{ path: string; rows: number; excluded: number } | null>(null)
const exporting = ref(false)

async function doExport() {
  exporting.value = true
  try {
    exportResult.value = await api.post<{ path: string; rows: number; excluded: number }>(
      '/companies/export',
      {
        format: exportForm.value.format,
        status: exportForm.value.status || null,
        country: exportForm.value.country || null,
      },
    )
  } finally {
    exporting.value = false
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
  margin: 0 0 10px;
}
.result {
  margin-top: 12px;
}
</style>
