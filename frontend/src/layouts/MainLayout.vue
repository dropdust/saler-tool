<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="brand">销售获客工具</div>
      <el-menu :default-active="activePath" router class="menu">
        <el-menu-item index="/">
          <el-icon><Odometer /></el-icon><span>总览</span>
        </el-menu-item>
        <el-sub-menu index="seeds">
          <template #title><el-icon><Share /></el-icon><span>种子知识库</span></template>
          <el-menu-item index="/seeds">种子列表</el-menu-item>
          <el-menu-item index="/seeds/review">待审核</el-menu-item>
          <el-menu-item index="/seeds/graph">图谱视图</el-menu-item>
          <el-menu-item index="/seeds/graph-manage">图谱管理</el-menu-item>
          <el-menu-item index="/seeds/stats">产量统计</el-menu-item>
          <el-menu-item index="/seeds/import-export">导入与回灌</el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="leads">
          <template #title><el-icon><User /></el-icon><span>客户线索</span></template>
          <el-menu-item index="/leads">客户列表</el-menu-item>
          <el-menu-item index="/leads/jobs">挖掘任务</el-menu-item>
          <el-menu-item index="/leads/domains">候选域名</el-menu-item>
          <el-menu-item index="/leads/import-export">导入与导出</el-menu-item>
          <el-menu-item index="/leads/exclusions">排除规则</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/content">
          <el-icon><Document /></el-icon><span>营销内容</span>
        </el-menu-item>
        <el-menu-item index="/channels">
          <el-icon><Message /></el-icon><span>营销通道</span>
        </el-menu-item>
        <el-menu-item index="/campaigns">
          <el-icon><Promotion /></el-icon><span>营销计划</span>
        </el-menu-item>
        <el-sub-menu index="settings">
          <template #title><el-icon><Setting /></el-icon><span>设置</span></template>
          <el-menu-item index="/settings">通用设置</el-menu-item>
          <el-menu-item index="/settings/llm">大模型服务</el-menu-item>
          <el-menu-item index="/settings/search">检索渠道</el-menu-item>
          <el-menu-item index="/settings/suppressions">退订黑名单</el-menu-item>
          <el-menu-item index="/settings/backup">备份与数据</el-menu-item>
          <el-menu-item index="/settings/about">关于与联系</el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="page-title">{{ pageTitle }}</span>
        <span class="spacer" />
        <TaskCenter />
        <el-tag v-if="appStore.health" type="success" effect="plain">
          本地服务运行中 · v{{ appStore.health.version }}
        </el-tag>
        <el-tag v-else type="danger" effect="plain">本地服务不可用</el-tag>
        <el-switch
          v-model="isDark"
          data-test="theme-switch"
          inline-prompt
          :active-icon="Moon"
          :inactive-icon="Sunny"
          :aria-label="`主题切换：当前${isDark ? '深色' : '浅色'}模式`"
        />
      </el-header>
      <el-main class="main"><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import {
  Document,
  Message,
  Moon,
  Odometer,
  Promotion,
  Setting,
  Share,
  Sunny,
  User,
} from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app'
import { useJobCenterStore } from '../stores/jobCenter'
import { useThemeStore } from '../stores/theme'
import TaskCenter from '../components/common/TaskCenter.vue'

const route = useRoute()
const appStore = useAppStore()
const jobCenter = useJobCenterStore()
const themeStore = useThemeStore()
const activePath = computed(() => route.path)
const pageTitle = computed(() => (route.meta.title as string) ?? '')
const isDark = computed({
  get: () => themeStore.current === 'dark',
  set: (value: boolean) => {
    if ((themeStore.current === 'dark') !== value) themeStore.toggle()
  },
})

onMounted(() => {
  appStore.loadHealth()
  appStore.loadSettings().catch(() => undefined)
  // 应用启动即接管任务状态：拉取活跃/最近终态并对活跃任务重连 SSE（刷新恢复，FR-006）
  jobCenter.init().catch(() => undefined)
})
</script>

<style scoped>
.layout {
  height: 100vh;
}
.aside {
  border-right: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
}
.brand {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 16px;
  border-bottom: 1px solid var(--el-border-color-light);
}
.menu {
  border-right: none;
  flex: 1;
  overflow-y: auto;
}
.header {
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--el-border-color-light);
  gap: 12px;
}
.page-title {
  font-size: 15px;
  font-weight: 600;
}
.spacer {
  flex: 1;
}
.main {
  background: var(--el-fill-color-lighter);
}
</style>
