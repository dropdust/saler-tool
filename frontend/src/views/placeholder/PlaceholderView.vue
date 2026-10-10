<template>
  <div>
    <PageHeader :title="title" description="该模块将在后续里程碑提供（进度见 specs/001-sales-tool/tasks.md）。" />
    <el-card shadow="never">
      <EmptyState :description="`${title} — 建设中`" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '../../components/common/PageHeader.vue'
import EmptyState from '../../components/common/EmptyState.vue'

const route = useRoute()
const title = computed(() => (route.meta.title as string) ?? '模块')
</script>
