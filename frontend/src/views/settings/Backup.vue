<template>
  <div>
    <PageHeader
      title="备份与数据"
      description="备份/恢复数据资产（数据主权）；全量导出为开放格式，供未来企业版迁移。"
    >
      <template #actions>
        <el-button type="primary" :loading="backingUp" @click="createBackup">创建备份</el-button>
        <el-button :loading="exporting" @click="exportAll">全量导出</el-button>
        <el-button @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="items">
        <el-table-column prop="path" label="备份文件" min-width="320" show-overflow-tooltip />
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ formatSize(row.size_bytes) }}</template>
        </el-table-column>
        <el-table-column prop="schema_version" label="schema" width="120" />
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ row.created_at ? row.created_at.slice(0, 19).replace('T', ' ') : '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="validate(row as BackupRow)">校验</el-button>
            <el-button size="small" text type="warning" @click="restore(row as BackupRow)">恢复</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !items.length" :image-size="70" description="暂无备份：点击右上角「创建备份」" />
    </el-card>

    <el-alert
      class="tip"
      type="info"
      show-icon
      :closable="false"
      title="恢复会整体替换当前数据库（旧库自动留档为 saler.db.pre-restore-*）；恢复或迁移目录后建议重启应用。"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ApiError, api } from '../../api/client'
import { watchJob } from '../../api/jobs'
import PageHeader from '../../components/common/PageHeader.vue'

interface BackupRow {
  id: number
  path: string
  kind: string
  size_bytes: number
  schema_version: string | null
  created_at: string | null
}

const items = ref<BackupRow[]>([])
const loading = ref(false)
const backingUp = ref(false)
const exporting = ref(false)

function formatSize(bytes: number): string {
  if (bytes > 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  if (bytes > 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

async function load() {
  loading.value = true
  try {
    const page = await api.get<{ items: BackupRow[] }>('/backups', { page_size: 50 })
    items.value = page.items
  } finally {
    loading.value = false
  }
}

async function createBackup() {
  backingUp.value = true
  try {
    const { job_id } = await api.post<{ job_id: number }>('/backups', {})
    const job = await watchJob(job_id)
    if (job.status === 'completed') {
      ElMessage.success(`备份完成：${job.result?.path ?? ''}`)
      await load()
    } else {
      ElMessage.error(job.error ?? '备份失败')
    }
  } finally {
    backingUp.value = false
  }
}

async function exportAll() {
  exporting.value = true
  try {
    const { job_id } = await api.post<{ job_id: number }>('/export/all', {})
    const job = await watchJob(job_id)
    if (job.status === 'completed') {
      ElMessage.success(`全量导出完成：${job.result?.path ?? ''}`)
    } else {
      ElMessage.error(job.error ?? '导出失败')
    }
  } finally {
    exporting.value = false
  }
}

async function validate(row: BackupRow) {
  const body = await api.post<{ ok: boolean; manifest: { schema_version: string | null } }>(
    '/backups/validate',
    { path: row.path },
  )
  ElMessage.success(`校验通过（schema ${body.manifest.schema_version ?? '未知'}）`)
}

async function restore(row: BackupRow) {
  await ElMessageBox.confirm(
    `将把数据整体恢复到该备份时点：\n${row.path}\n\n当前数据会以 saler.db.pre-restore-* 留档；恢复后建议重启应用。`,
    '确认恢复',
    { type: 'warning', confirmButtonText: '恢复' },
  )
  const { job_id } = await api.post<{ job_id: number }>('/restore', { path: row.path })
  try {
    const job = await watchJob(job_id)
    if (job.status === 'completed') {
      ElMessage.success('恢复完成：数据库已整体替换，建议重启应用')
    } else {
      ElMessage.error(job.error ?? '恢复失败')
    }
  } catch (error) {
    // 恢复替换整库后任务记录可能不可见（404）——视为已完成
    if (error instanceof ApiError && error.code === 'not_found') {
      ElMessage.success('恢复完成（数据库已整体替换），建议重启应用')
    } else {
      throw error
    }
  }
  await load()
}

onMounted(load)
</script>

<style scoped>
.tip {
  margin-top: 12px;
}
</style>
