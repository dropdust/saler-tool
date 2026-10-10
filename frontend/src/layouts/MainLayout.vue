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
        <el-menu-item index="/leads">
          <el-icon><User /></el-icon><span>客户线索</span>
        </el-menu-item>
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
        </el-sub-menu>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="page-title">{{ pageTitle }}</span>
        <span class="spacer" />
        <el-tag v-if="appStore.health" type="success" effect="plain">
          本地服务运行中 · v{{ appStore.health.version }}
        </el-tag>
        <el-tag v-else type="danger" effect="plain">本地服务不可用</el-tag>
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
  Odometer,
  Promotion,
  Setting,
  Share,
  User,
} from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app'

const route = useRoute()
const appStore = useAppStore()
const activePath = computed(() => route.path)
const pageTitle = computed(() => (route.meta.title as string) ?? '')

onMounted(() => {
  appStore.loadHealth()
  appStore.loadSettings().catch(() => undefined)
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
