# Implementation Plan: 应用前端主题（浅色 / 深色）

**Branch**: `002-frontend-theme` | **Date**: 2026-10-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-frontend-theme/spec.md`

## Summary

为应用前端增加 light / dark 两种主题模式（FR-001~013）：主界面提供全局一步切换控件，切换即时全局生效且不中断操作；主题偏好持久化于本地设置数据（随备份/恢复与迁移保留）；启动首屏直接以目标主题渲染、无可感知闪变；两种主题覆盖全部界面，营销内容预览与用户素材保持"收件人视角"保真。

技术路线（决策依据见 [research.md](research.md)）：采用 **Element Plus 官方暗色主题变量**（`theme-chalk/dark/css-vars.css` + `html.dark` 类，**零新增依赖**）——前端现况已基本基于 `--el-*` CSS 变量（仅图谱视图 5 处硬编码色），适配面收敛；主题偏好存为**后端设置 KV 新键 `ui_theme`**（单一事实源：随 `saler.db` 整库备份/迁移自动保留，且不依赖 WebView 存储）；首屏零闪变通过**后端在 `GET /` 注入 `html.dark` 类**实现（应用为 hash 路由，HTML 入口唯一，注入点单一可靠）；ECharts 图谱视图（canvas 不受 CSS 变量影响）按主题色板重渲染适配；内容预览区固定"收件人视角"浅色基底。

## Technical Context

**Language/Version**: TypeScript 5.6 + Vue 3.5（前端）；Python ≥ 3.12（后端，两处小改动）

**Primary Dependencies**: Element Plus 2.8.8 官方暗色主题 CSS 变量（包内既有能力，无新增依赖）；ECharts 5.5（既有，图谱视图主题化）；FastAPI / StaticFiles（HTML 入口注入路由）

**Storage**: SQLite `app_setting` KV 表新增已知键 `ui_theme`（枚举 `light` | `dark`，默认 `light`）；**无 schema 迁移**（默认值走 `settings_service.DEFAULTS`，行在首次切换时创建）

**Testing**: vitest（前端：主题 store、归一/守卫、调色板纯函数、DOM 类切换）；pytest（后端：`GET /` 注入行为单测、settings 契约新增键）；视觉适配与对比度为 quickstart 固定清单走查（T3）

**Target Platform**: Windows（WebView2）/ macOS（WKWebView）/ Linux（WebKitGTK）三平台桌面壳；`--server` 浏览器模式同一路径生效

**Project Type**: desktop-app（前后端增量特性）

**Performance Goals**: 切换即时生效（同帧 DOM 类翻转；整体呈现 ≤ 1s，SC-001）；启动零闪变（服务端注入，SC-005）；启动路径新增开销 = 单行 KV 读取（亚毫秒级）

**Constraints**:
- 纯展示层变更（FR-013）：不触发业务数据与对外调用；唯一写入为偏好 KV
- 不得新增第三方依赖（EP 暗色变量与 ECharts 均为既有能力）
- pywebview 未配置 WebView storage_path → localStorage 等不可作持久化依据，**后端 KV 为唯一事实源**
- 已知限制：Vite dev 模式（无注入）启动可能瞬时 light→dark（仅开发期；壳形态验收，前端 `syncFromServer` 兜底）

**Scale/Scope**: 全部主界面（约 10–12 个路由页 + 布局/弹窗/空态/图表组件）；2 个主题；1 个设置键；前端新增 3 个单元（store / palette / theme.css），后端改动 2 处

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 要求摘要 | 本特性对照 | 结论 |
|---|---|---|---|
| I. 测试驱动开发 | 红→绿→重构；测试分层齐备 | 每个实现任务先落失败测试：前端 vitest（store 翻转/持久化/守卫/归一、palette 纯函数）；后端 pytest（注入路由：dark/light/非法回退/no-store；settings 契约：默认值/值域校验）；视觉走查固定清单入 quickstart（T3） | PASS（按计划） |
| II. 对象与封装 | 前端以组件为边界；视图只依赖本地 API 契约 | 主题状态与持久化收敛于 `stores/theme.ts`（唯一 DOM 类操作者）；palette 为纯函数；视图只消费 store；后端注入走 `settings_service`（仓储模式），不引入新耦合 | PASS（按计划） |
| III. 约定大于配置 | 默认开箱即用；扩展点零配置；契约同步 | `ui_theme` 注册进 `settings_service.DEFAULTS`（复用"未知键拒绝"约定）；默认 light 零配置；值域校验作为 settings 校验钩子（约定式扩展点）；契约增量入 `contracts/theme-contract.md` 并同步 001 `local-api.md` | PASS（按计划） |
| IV. 技术栈限定 | 不引入新语言/框架；拒绝依赖膨胀 | **零新增依赖**：EP 暗色变量为既有包内置；图表为既有 ECharts | PASS |
| V. 密钥零入库 | 密钥不入代码/日志/导出 | 本特性不涉及任何凭证；主题值非敏感数据，无脱敏面 | PASS（不适用） |
| 附加约束 | 离线可用；数据主权；中文界面；Web 演进兼容 | 主题完全离线、纯本地；不触碰任何对外调用路径；控件文案中文；契约为加性演进（新增 KV 键），兼容未来 Web 版 | PASS |
| 工作流质量门 | 逐任务提交；契约同步；关键变更后 analyze | 计划含契约/文档同步任务（001 local-api.md、001 quickstart S1 增量）；实现按 tasks.md 逐任务提交 | PASS（按计划） |

**Phase 1 设计复核**：data-model.md / contracts/theme-contract.md / quickstart.md 与上表逐条对照，无违反项；Complexity Tracking 为空。

## Project Structure

### Documentation (this feature)

```text
specs/002-frontend-theme/
├── plan.md              # 本文件（/speckit-plan 输出）
├── research.md          # Phase 0 输出：7 项技术决策（机制/持久化/零闪变/控件/图表/对比度/测试）
├── data-model.md        # Phase 1 输出：ui_theme 偏好实体与运行时状态机
├── quickstart.md        # Phase 1 输出：验证场景 T1–T6（含冻结包冒烟增量）
├── contracts/
│   └── theme-contract.md    # Phase 1 输出：设置键增量 + HTML 入口注入行为 + 前端主题契约
└── tasks.md             # Phase 2 输出（/speckit-tasks 生成，不在本阶段）
```

### Source Code (repository root)

```text
frontend/
├── src/
│   ├── main.ts                      # 修改：import EP dark css-vars + theme.css；启动 syncFromServer 挂接
│   ├── styles/theme.css             # 新增：html/body 基底、color-scheme 双态、图表主题变量（亮/暗双套）、预览保真基底
│   ├── stores/theme.ts              # 新增：主题 store（current/toggle/syncFromServer；唯一 DOM 类操作者）
│   ├── theme/palette.ts             # 新增：调色板/归一纯函数（读 computed CSS 变量，供 ECharts 与测试）
│   ├── layouts/MainLayout.vue       # 修改：页头新增主题切换控件（全局一步可达、当前态可辨识）
│   └── views/seeds/GraphView.vue    # 修改：ECharts 色板/标签/工具提示/边线/图例主题化 + 监听主题重渲染
└── tests/
    ├── theme-store.test.ts          # 新增：翻转/PUT 调用与失败保留/同步守卫/归一
    └── theme-palette.test.ts        # 新增：palette 纯函数与归一规则

backend/
├── src/saler/
│   ├── services/settings_service.py # 修改：DEFAULTS + "ui_theme": "light"；值域校验钩子 validate_value
│   └── api/main.py                  # 修改：dist 存在时注册显式 GET "/"（注入 html.dark、no-store；异常回退 light），StaticFiles 挂载其后
└── tests/
    ├── unit/test_theme_injection.py     # 新增：dark 注入/light 原样/非法值回退/no-store/资源不受影响
    └── contract/test_settings_api.py    # 新增：ui_theme 默认值、写入、非法值 400

specs/001-sales-tool/                # 契约与文档同步（宪法"契约变更必须同步"）
├── contracts/local-api.md           # 修改：settings 行补记 ui_theme 键与值域
└── quickstart.md                    # 修改：S1 增补"首启默认 light + 页头切换可达"断言
```

**Structure Decision**: 沿用既有前后端单体布局（`backend/` + `frontend/`），无新模块边界。前端主题逻辑收敛为 3 个新增单元（store / palette / theme.css）+ 2 处接入点（main.ts、MainLayout）；后端仅动 settings 默认表与 API 入口路由 2 处；契约/文档同步回 001 两处。

## Complexity Tracking

> 无宪法违反项，本表为空。
