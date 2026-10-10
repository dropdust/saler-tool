<template>
  <div v-loading="loading">
    <PageHeader
      :title="`版本历史 · ${langLabel(variant?.lang)}`"
      description="修改与恢复都会生成新版本（完整审计链）；恢复旧版本 = 以旧内容创建新版本。"
    >
      <template #actions>
        <el-button @click="router.push(`/content/variants/${variantId}`)">返回编辑</el-button>
        <el-button @click="router.push('/content')">主题列表</el-button>
      </template>
    </PageHeader>

    <el-card shadow="never">
      <el-table :data="versions">
        <el-table-column label="版本" width="110">
          <template #default="{ row }">
            v{{ row.version_no }}
            <el-tag v-if="row.version_no === currentVersionNo" size="small" type="success" class="tag">当前</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ (row.created_at || '').slice(0, 19).replace('T', ' ') }}</template>
        </el-table-column>
        <el-table-column label="创建者" width="90">
          <template #default="{ row }">{{ row.created_by === 'llm' ? 'AI' : '用户' }}</template>
        </el-table-column>
        <el-table-column prop="change_note" label="变更说明" min-width="180" show-overflow-tooltip />
        <el-table-column label="变量" min-width="180">
          <template #default="{ row }">
            <el-tag v-for="name in row.variables" :key="name" size="small" class="chip">{{ name }}</el-tag>
            <span v-if="!row.variables.length" class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="view(row as ContentVersionRow)">查看</el-button>
            <el-button
              v-if="row.version_no !== currentVersionNo"
              size="small"
              text
              type="warning"
              @click="restore(row as ContentVersionRow)"
            >
              恢复
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="viewVisible" :title="`版本 v${viewing?.version_no ?? ''}`" width="640px">
      <div v-if="viewing">
        <div class="meta">
          {{ (viewing.created_at || '').slice(0, 19).replace('T', ' ') }}
          · {{ viewing.created_by === 'llm' ? 'AI' : '用户' }}
          · {{ viewing.change_note || '（无说明）' }}
        </div>
        <div v-if="viewing.subject" class="subject">
          <span class="label">主题行：</span>{{ viewing.subject }}
        </div>
        <pre class="body">{{ viewing.body_md || '（空）' }}</pre>
      </div>
      <template #footer>
        <el-button @click="viewVisible = false">关闭</el-button>
        <el-button
          v-if="viewing && viewing.version_no !== currentVersionNo"
          type="warning"
          @click="restore(viewing)"
        >
          恢复为新版本
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../../api/client'
import type { ContentVariantRow, ContentVersionRow } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'
import { langLabel } from '../../constants'

const route = useRoute()
const router = useRouter()
const variantId = Number(route.params.id)

const loading = ref(false)
const variant = ref<ContentVariantRow | null>(null)
const versions = ref<ContentVersionRow[]>([])
const viewVisible = ref(false)
const viewing = ref<ContentVersionRow | null>(null)

const currentVersionNo = computed(() => variant.value?.current?.version_no ?? null)

async function load() {
  loading.value = true
  try {
    variant.value = await api.get<ContentVariantRow>(`/content/variants/${variantId}`)
    versions.value = await api.get<ContentVersionRow[]>(`/content/variants/${variantId}/versions`)
  } finally {
    loading.value = false
  }
}

function view(row: ContentVersionRow) {
  viewing.value = row
  viewVisible.value = true
}

async function restore(row: ContentVersionRow) {
  try {
    await ElMessageBox.confirm(
      `恢复 v${row.version_no}：将以该版本内容创建一个新版本（v${(currentVersionNo.value ?? 0) + 1}），历史不受影响。`,
      '恢复历史版本',
      { type: 'warning', confirmButtonText: '恢复为新版本', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  await api.post(`/content/variants/${variantId}/restore`, { version_no: row.version_no })
  ElMessage.success('已恢复为新版本')
  viewVisible.value = false
  await load()
}

onMounted(load)
</script>

<style scoped>
.tag {
  margin-left: 6px;
}
.chip {
  margin-right: 4px;
}
.muted {
  color: var(--el-text-color-secondary);
}
.meta {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-bottom: 10px;
}
.subject {
  font-weight: 600;
  margin-bottom: 8px;
}
.subject .label {
  color: var(--el-text-color-secondary);
  font-weight: 400;
}
.body {
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 12px;
  margin: 0;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.6;
}
</style>
