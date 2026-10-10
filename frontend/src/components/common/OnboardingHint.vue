<template>
  <el-card v-if="!dismissed" shadow="never" class="onboarding">
    <template #header>
      <div class="head">
        <strong>{{ title }}</strong>
        <el-button size="small" text @click="dismiss">不再提示</el-button>
      </div>
    </template>
    <ol class="steps">
      <li v-for="(step, index) in steps" :key="index" :class="{ done: completed[index] }">{{ step }}</li>
    </ol>
    <div v-if="hint" class="hint">{{ hint }}</div>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(
  defineProps<{
    title?: string
    steps?: string[]
    completed?: boolean[]
    hint?: string
    storageKey?: string
  }>(),
  {
    title: '操作指引',
    steps: () => [],
    completed: () => [],
    hint: '',
    storageKey: '',
  },
)
const emit = defineEmits<{ dismissed: [] }>()

const dismissed = ref(props.storageKey ? localStorage.getItem(props.storageKey) === '1' : false)

function dismiss() {
  dismissed.value = true
  if (props.storageKey) localStorage.setItem(props.storageKey, '1')
  emit('dismissed')
}
</script>

<style scoped>
.onboarding {
  margin-bottom: 12px;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.steps {
  margin: 0;
  padding-left: 18px;
  line-height: 1.9;
}
.steps li.done {
  color: var(--el-color-success);
}
.hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
