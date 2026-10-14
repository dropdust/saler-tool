<template>
  <el-tag :type="tagType" effect="light" size="small">{{ label }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ status: string; domain?: 'review' }>()
const { t, te } = useI18n()

const TYPES: Record<string, string> = {
  pending: 'info',
  running: 'primary',
  done: 'success',
  invalid: 'danger',
  approved: 'success',
  rejected: 'danger',
  queued: 'info',
  paused: 'warning',
  completed: 'success',
  failed: 'danger',
  cancelled: 'info',
  interrupted: 'warning',
}

type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'
const tagType = computed<TagType>(() => (TYPES[props.status] as TagType) ?? 'info')

// 审核域：review_status=pending 与执行状态 pending 共用同值，但标签应为"待审核"（T194，与筛选下拉口径一致）
const labelKey = computed(() =>
  props.domain === 'review' && props.status === 'pending' ? 'status.review' : `status.${props.status}`,
)
const label = computed(() => (te(labelKey.value) ? t(labelKey.value) : props.status))
</script>
