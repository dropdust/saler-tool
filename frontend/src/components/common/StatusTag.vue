<template>
  <el-tag :type="tagType" effect="light" size="small">{{ label }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ status: string }>()
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
}

type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'
const tagType = computed<TagType>(() => (TYPES[props.status] as TagType) ?? 'info')
const label = computed(() => (te(`status.${props.status}`) ? t(`status.${props.status}`) : props.status))
</script>
