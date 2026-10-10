<template>
  <el-auto-resizer :class="'virtual-table'">
    <template #default="{ height, width }">
      <el-table-v2
        :key="`${width}-${data.length}`"
        :columns="columns"
        :data="data"
        :width="width || 800"
        :height="height || 480"
        :row-height="rowHeight"
        :row-key="rowKey"
        fixed
        :header-height="40"
      />
    </template>
  </el-auto-resizer>
</template>

<script setup lang="ts">
/**
 * 大列表虚拟滚动表格（T133）：基于 el-table-v2，仅渲染可视行。
 * 适用于 10 万级线索列表的只读浏览（列渲染经 cellRenderer 提供）。
 */

withDefaults(
  defineProps<{
    // el-table-v2 列定义（含 cellRenderer）；EP 未从包根导出该类型，这里放宽以兼容官方类型
    columns: any[]
    data: any[]
    rowHeight?: number
    rowKey?: any
  }>(),
  {
    rowHeight: 44,
    rowKey: 'id',
  },
)
</script>

<style scoped>
.virtual-table {
  height: 100%;
  min-height: 360px;
}
</style>
