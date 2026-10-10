<template>
  <el-empty :description="description || '暂无数据'" :image-size="80" />
</template>

<script setup lang="ts">
defineProps<{ description?: string }>()
</script>
