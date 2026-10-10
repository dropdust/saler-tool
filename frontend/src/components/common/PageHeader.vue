<template>
  <div class="page-header">
    <div>
      <h2 class="title">{{ title }}</h2>
      <p v-if="description" class="description">{{ description }}</p>
    </div>
    <div class="actions"><slot name="actions" /></div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 12px;
}
.title {
  margin: 0;
  font-size: 18px;
}
.description {
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
</style>
