import { createRouter, createWebHashHistory } from 'vue-router'
import MainLayout from '../layouts/MainLayout.vue'

const Placeholder = () => import('../views/placeholder/PlaceholderView.vue')

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      component: MainLayout,
      children: [
        {
          path: '',
          name: 'dashboard',
          component: () => import('../views/dashboard/Dashboard.vue'),
          meta: { title: '总览' },
        },
        {
          path: 'seeds',
          name: 'seeds',
          component: () => import('../views/seeds/SeedList.vue'),
          meta: { title: '种子列表' },
        },
        {
          path: 'seeds/review',
          name: 'seeds-review',
          component: () => import('../views/seeds/ReviewQueue.vue'),
          meta: { title: '待审核' },
        },
        {
          path: 'seeds/graph',
          name: 'seeds-graph',
          component: () => import('../views/seeds/GraphView.vue'),
          meta: { title: '图谱视图' },
        },
        {
          path: 'seeds/graph-manage',
          name: 'seeds-graph-manage',
          component: () => import('../views/seeds/GraphManage.vue'),
          meta: { title: '图谱管理' },
        },
        {
          path: 'seeds/stats',
          name: 'seeds-stats',
          component: () => import('../views/seeds/StatsPanel.vue'),
          meta: { title: '产量统计' },
        },
        {
          path: 'seeds/import-export',
          name: 'seeds-io',
          component: () => import('../views/seeds/ImportExport.vue'),
          meta: { title: '导入与回灌' },
        },
        {
          path: 'leads',
          name: 'leads',
          component: () => import('../views/leads/CompanyList.vue'),
          meta: { title: '客户列表' },
        },
        {
          path: 'leads/companies/:id',
          name: 'leads-company-detail',
          component: () => import('../views/leads/CompanyDetail.vue'),
          meta: { title: '客户详情' },
        },
        {
          path: 'leads/jobs',
          name: 'leads-jobs',
          component: () => import('../views/leads/CrawlJobs.vue'),
          meta: { title: '挖掘任务' },
        },
        {
          path: 'leads/domains',
          name: 'leads-domains',
          component: () => import('../views/leads/DomainList.vue'),
          meta: { title: '候选域名' },
        },
        {
          path: 'leads/import-export',
          name: 'leads-io',
          component: () => import('../views/leads/ImportExport.vue'),
          meta: { title: '导入与导出' },
        },
        {
          path: 'leads/exclusions',
          name: 'leads-exclusions',
          component: () => import('../views/leads/ExclusionRules.vue'),
          meta: { title: '排除规则' },
        },
        { path: 'content', component: Placeholder, meta: { title: '营销内容（后续里程碑）' } },
        { path: 'channels', component: Placeholder, meta: { title: '营销通道（后续里程碑）' } },
        { path: 'campaigns', component: Placeholder, meta: { title: '营销计划（后续里程碑）' } },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('../views/settings/General.vue'),
          meta: { title: '通用设置' },
        },
        {
          path: 'settings/llm',
          name: 'settings-llm',
          component: () => import('../views/settings/LlmProviders.vue'),
          meta: { title: '大模型服务' },
        },
        {
          path: 'settings/backup',
          name: 'settings-backup',
          component: () => import('../views/settings/Backup.vue'),
          meta: { title: '备份与数据' },
        },
        {
          path: 'settings/search',
          name: 'settings-search',
          component: () => import('../views/settings/SearchProviders.vue'),
          meta: { title: '检索渠道' },
        },
      ],
    },
  ],
})

export default router
