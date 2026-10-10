<template>
  <div>
    <PageHeader title="总览" description="本地优先销售工作台：种子知识库 → 客户线索 → 营销内容 → 通道 → 计划。" />
    <el-row :gutter="16">
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>本地服务</template>
          <template v-if="appStore.health">
            <el-tag type="success" effect="plain">运行中</el-tag>
            <span class="meta">版本 v{{ appStore.health.version }}</span>
          </template>
          <el-tag v-else type="danger" effect="plain">不可用</el-tag>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>种子知识库</template>
          <div class="stat">
            <span class="num">{{ seedTotal }}</span>
            <span class="meta">条种子（待审核 {{ reviewPending }}）</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>下一步</template>
          <el-button type="primary" @click="router.push('/seeds')">进入种子库</el-button>
          <el-button @click="router.push('/seeds/graph')">查看图谱</el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api/client'
import { useAppStore } from '../../stores/app'
import PageHeader from '../../components/common/PageHeader.vue'
import type { Paginated, Seed } from '../../api/types'

const router = useRouter()
const appStore = useAppStore()
const seedTotal = ref('—')
const reviewPending = ref('—')

onMounted(async () => {
  try {
    const all = await api.get<Paginated<Seed>>('/seeds', { page: 1, page_size: 1 })
    seedTotal.value = String(all.total)
    const pending = await api.get<Paginated<Seed>>('/seeds', {
      review_status: 'pending',
      page: 1,
      page_size: 1,
    })
    reviewPending.value = String(pending.total)
  } catch {
    seedTotal.value = '—'
  }
})
</script>

<style scoped>
.stat .num {
  font-size: 28px;
  font-weight: 600;
  margin-right: 8px;
}
.meta {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
