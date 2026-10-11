# Phase 0 Research: 应用前端主题（浅色 / 深色）

**Feature**: `002-frontend-theme` | **Date**: 2026-10-11 | 上游：[spec.md](spec.md) / [plan.md](plan.md)

技术上下文中的未知项均在编写本文件前解析完毕（无遗留 NEEDS CLARIFICATION）。以下为 7 项关键决策。

---

## R1 主题实现机制：Element Plus 官方暗色变量 + `html.dark` 类

**Decision**: 在 `frontend/src/main.ts` 静态引入 `element-plus/theme-chalk/dark/css-vars.css`；运行时主题载体为 `<html>` 上的 `dark` 类；全部组件样式继续只使用 `--el-*` CSS 变量。

**Rationale**:
- 现况核查：前端组件样式已高度基于 `--el-*` 变量（全仓硬编码颜色仅 GraphView.vue 5 处），接入官方暗色变量后大部分界面自动适配，改动面收敛。
- EP 2.8.8 内置亮/暗双套完整变量（含 `color-scheme`），组件级适配成熟、无自研色板维护成本。
- 零新增依赖（包内既有能力），符合宪法 IV。

**Alternatives considered**:
- 自研 design token 体系（工作量与维护成本高，收益不足）——否决；
- SCSS 编译期双主题（构建复杂化且无法运行时瞬时切换）——否决；
- 仅 `prefers-color-scheme` 媒体查询（无法满足"手动两种模式"）——否决。

## R2 偏好持久化：后端设置 KV（`app_setting.ui_theme`）为唯一事实源

**Decision**: 新增已知键 `ui_theme`（枚举 `light`/`dark`，默认 `light`，注册于 `settings_service.DEFAULTS`）；切换时 `PUT /api/v1/settings`。PUT 失败时保留会话内已应用主题并提示"偏好未保存（下次启动将回退）"——切换即时性（FR-003）优先于持久化反馈。

**Rationale**:
- 备份 = `saler.db` 整库一致性快照、迁移 = 整个数据目录复制 → KV 行随备份/恢复/迁移自动保留，FR-012 零额外实现。
- pywebview 未配置 WebView `storage_path`，localStorage/cookie 持久性不可靠，不能作为持久化依据。
- 沿用既有 settings API 契约与"未知键拒绝"约定，天然满足宪法 III；前端切换复用既有 `PUT /settings` 通道，无新接口。

**Alternatives considered**:
- localStorage（持久性不可靠；且需与后端镜像双写与对账，复杂度高）——否决；
- 独立配置文件（绕过 settings API，不入备份链，迁移丢失）——否决；
- cookie（与 localStorage 同类存储问题）——否决。

## R3 首屏零闪变：后端在 `GET /` 注入 `html.dark` 类

**Decision**: 在 `create_app` 中、`StaticFiles` 挂载**之前**，当 `frontend_dist` 存在时注册显式 `GET /` 路由：同步读取 `ui_theme`（任何异常回退 `light`，并归一非法值），将 `index.html` 的 `<html …>` 起始标签注入 `class="dark"`（light 时原样返回）；响应带 `Cache-Control: no-store`。静态资源仍由 StaticFiles 挂载服务。

**Rationale**:
- 应用使用 hash 路由（`createWebHashHistory`）：HTML 入口唯一（仅 `/`，含 `?token=` 场景），无 SPA 深链回退需求，注入点单一可靠。
- 主题在字节到达 WebView 前已正确 → 首帧即目标主题，FR-007/SC-005 由构造保证，且可在后端单测中断言。
- 同步读 SQLite 单行，开销可忽略；`--server` 浏览器模式同一路径生效。
- 现有 `test_spa_mount.py` 语义保持：light 默认时输出原样，无产物时 `/` 仍 404。

**Alternatives considered**:
- 前端挂载前 gating fetch（首屏前空白窗口；窗口底色由平台 WebView 决定，可能仍被感知为闪变，FR-007 仅"大概率"满足）——否决（作为 dev 模式兜底存在的形式保留）；
- localStorage 镜像 + inline script（依赖不可靠存储，同 R2；恢复/迁移后镜像缺失仍需回退路径）——否决；
- 服务端注入 `<style>` 强制变量（与类注入同点位，无额外收益）——否决。

**已知限制**: Vite dev（`SALER_DEV_URL`/直接 5173）无注入 → 启动可能瞬时 light→dark；由前端 `syncFromServer` 兜底（R4），仅开发期现象，记入 quickstart 排查表。

## R4 切换控件与前端状态：`stores/theme.ts`（唯一 DOM 类操作者）+ 页头控件

**Decision**: Pinia store `useThemeStore`：
- `current: 'light' | 'dark'`，初始值从 `document.documentElement.classList` 读取（生产环境 = 服务端注入值）；
- `toggle()`：同帧翻转 DOM 类 → `PUT /settings{values:{ui_theme}}`；
- `syncFromServer()`：启动时读 `/settings`，仅在 `userTouched === false` 且与 DOM 不一致时校正（覆盖 dev 模式与极端恢复场景），防启动竞态覆盖用户刚做的切换。

控件置于 `MainLayout.vue` 页头（所有页面一步可达；`el-switch` 内联 ☀️/🌙 图标指示当前态，中文 aria 标签）。**禁止**任何视图直接操作 DOM 类。

**Rationale**: 运行时事实（DOM 类）与持久化事实（KV）在启动时对齐、切换后立即一致；逻辑集中于单一 store，组件仅消费，满足宪法 II；jsdom 可完整单测。

**Alternatives considered**: 各组件自读变量（状态分散、无法统一重渲图表）——否决；仅设置页入口（FR-002 全局一步可达不满足）——否决；系统托盘/快捷键（超出规格）——否决。

## R5 ECharts 图谱视图主题化

**Decision**: 新增 `frontend/src/theme/palette.ts` 纯函数层：经 `getComputedStyle(document.documentElement)` 读取 EP 变量构建调色板（节点状态色 ← `--el-color-success/warning/primary/info`；标签 ← `--el-text-color-primary`；工具提示 ← `--el-bg-color-overlay/--el-text-color-primary/--el-border-color`）；边线颜色改用 `styles/theme.css` 中定义的图表专用变量（`--chart-edge-solid/--chart-edge-dashed`，亮/暗双套）。GraphView 图例圆点同步改用变量，并 `watch(themeStore.current)` → 复用现 `renderChart()`（notMerge 全量 `setOption`，天然支持重渲）。

**Rationale**: canvas 绘制不消费 CSS 变量，必须显式取色；读 computed 值可在切换后自然取到新主题色；EP 状态色在暗色变量表有语义一致的暗色变体。

**Alternatives considered**: ECharts 内置 `'dark'` 主题（色板与 EP 不一致，且需注册两套 theme，切换更重）——否决；不处理图表（违反 FR-008/SC-002，深色下节点标签不可读）——否决。

## R6 对比度策略与视觉验收

**Decision**: 直接采用 EP 亮/暗两套官方变量（正文/次要文本对比度由 EP 设计体系保障）；对 `theme.css` 中新增的自定义样式逐一核色；在 quickstart T3 中以浏览器 DevTools 对比度检查抽查关键面（正文、次要文本、表格、状态标签、按钮文字）≥ 4.5:1，结果勾选留档。

**Rationale**: EP 暗色系为成熟 AA 级实现，自研全量校验脚本收益低；"固定清单抽查 + 留档"满足 SC-003 的可验证性要求。

**Alternatives considered**: 引入 axe-core/自研对比度扫描（依赖膨胀，且对 canvas/图表覆盖有限）——否决（可作为后续可选增强）。

## R7 测试与验证策略

**Decision**:
- 可自动化部分全部自动化：后端 pytest（注入路由单测 + settings 契约），前端 vitest（store / palette / 归一 / 守卫）；
- 视觉覆盖（SC-002/003/007）为 quickstart T3/T4 固定清单走查（每页勾选，缺陷数 0 为准）；
- 冻结包冒烟在既有 S1/S6/S10 基础上做"主题增量"（T6）。

**Rationale**: 主题覆盖本质包含视觉判断，自动化成本超本期收益（项目现无 E2E 基建，引入 Playwright 不符合"拒绝依赖膨胀"）；以固定清单保证走查可重复、结论可复核。DOM 类、持久化、注入、图表取色等全部逻辑面已由单测覆盖，视觉走查只承担"人眼可读性"职责。

**Alternatives considered**: 引入 Playwright/E2E 截图比对（新基建成本高，跨平台 WebView 渲染差异导致基线脆弱）——否决，留待后续如需。
