# Implementation Plan: 统一任务中心与任务后台化

**Branch**: `005-task-center` | **Date**: 2026-10-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-task-center/spec.md`

## Summary

长任务的**服务端后台执行**在 001 已交付（POST 立即 202 + 进程内协程 + `job` 台账 + SSE + 暂停/恢复/取消），本特性补齐三块缺口：

1. **前端全局任务中心（FR-001~008）**：新增单例 store 汇聚全部任务状态（启动即拉取活跃+最近终态、按活跃任务订阅既有 SSE、断线快照补齐），`MainLayout` 顶栏挂常驻入口（运行中数量徽标），点击展开任务抽屉（活跃任务列表/进度/阶段/耗时/暂停恢复取消/跳转；最近终态回看）。所有页内监控（挖掘任务页、计划监控页）与对话框轮询统一收敛到该 store——**同一任务全应用只有一份订阅、一处真相**；刷新/重进自动恢复展示，无需手动点「监控」。
2. **对话框任务转入后台（FR-009~013）**：4 个模态对话框动作（AI 扩充、种子翻译、内容起草、主题级多语言）的进行状态改由 store 驱动——关闭对话框任务继续、重开对话框直接呈现该进行中任务的实时状态（杜绝误重复启动）、留框等待体验不变；其余页面表单/按钮类入口（启动挖掘、检索扩充、回灌、名单导入、备份/恢复/导出、数据目录迁移、重试发送）同步收敛到 store：离开页面不中断，进度/终态经任务中心与通知呈现。
3. **状态真实性与重跑（FR-014~020）**：`create_app` 启动时对账——非终态任务一律标 `interrupted`（已中断），`crawl_job` 明细行同步；挖掘任务工厂全周期同步明细状态（修掉"失败停留在 queued"的既有缺陷）；按类型注册的**重新运行**（`POST /jobs/{id}/rerun`，仅"挖掘/回灌/导入"等断点安全类型）支撑中断后一键续跑（不重复抓取）；终态到达时经 `ElNotification` 全局通知（同一任务一次、用户主动取消不通知）。

**技术路线**：后端零新依赖——新增 `jobs/reconcile.py`（对账）、`jobs/catalog.py`（任务类型目录：pausable/rerunnable/重跑 starter 注册表，沿用仓库既有 registry 惯用法）；`TERMINAL_STATUSES` 纳入 `interrupted`；`/jobs` 支持逗号多状态过滤；SSE 终态快照映射修正（cancelled/interrupted 不再误发 done）。前端零新依赖——Pinia store + 既有 Element Plus（el-drawer/el-badge/ElNotification 均已在全量引入中）。无数据库迁移（`status` 列 String(20) 直接容纳 `interrupted`）。决策依据见 [research.md](research.md)。

## Technical Context

**Language/Version**: Python ≥ 3.12（后端）；TypeScript 5.x + Vue 3（前端）

**Primary Dependencies**: 既有栈——FastAPI、SQLAlchemy + Alembic、pywebview、Element Plus、Pinia、vue-router。本特性**零新增依赖**（Element Plus 全量引入已含 el-drawer/el-badge/ElNotification；SSE 走浏览器原生 EventSource，既有 `useJobEvents` 已用）

**Storage**: SQLite；**无表结构变更**（`job.status`/`crawl_job.status` 均为 String(20)，`interrupted` 为新增值域；无 Alembic 迁移）

**Testing**: pytest（对账单元、重跑注册表与守卫、`/jobs` 过滤与 SSE 快照契约、crawl 明细状态全周期——沿用"临时数据目录 + 假 Provider/假引擎"模式，离线可跑）；vitest（jobCenter store：订阅/合并/通知去重/刷新恢复/控制与重跑；TaskCenter 组件：徽标/抽屉/耗时/跳转；对话框重开呈现进行中态）；端到端沿用 001 CDP 验证配方（`--server` + 临时数据目录 + headless Chrome）

**Target Platform**: Windows / macOS / Linux 桌面（pywebview 壳 + 本地 FastAPI + SPA）；`--server` 无窗模式同覆盖

**Project Type**: desktop-app（三段式单仓：backend / frontend / packaging）

**Performance Goals**: 任务中心初始化 ≤ 2 个列表请求（活跃 + 最近终态）；SSE 连接数 = 活跃任务数（单用户常 ≤ 3）；徽标计数随事件 ≤ 1s 更新；通知不阻塞交互；抽屉列表有界（活跃全量 + 最近 20 条）

**Constraints**: 对外调用（检索/大模型/发送）不因重跑自动重放——重跑一律用户主动点击；复用既有 SSE 与事件总线，不新增常驻调度；页内监控视图保留为详情视图且与抽屉同源（FR-008）

**Scale/Scope**: 全部 15 种任务类型（crawl、campaign_send、ai_seed_expand/translate、ai_term_translate、ai_content_draft/translate、seed_discover、seed_validate、ingest_harvest、company_import、backup、restore、export_all、data_dir_move）；对话框动作入口 4 个（+ 页面级长任务入口 8 个）；活跃任务 ≤ 3

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 要求摘要 | 本特性对照 | 结论 |
| --- | --- | --- | --- |
| I. 测试驱动开发 | 红→绿→重构；测试分层齐备 | 后端：对账单测、重跑守卫/注册表单测、`/jobs` 过滤与 SSE 快照契约测试、crawl 状态全周期契约测试——全部先行失败；前端：store/组件/对话框行为 vitest 先行；端到端 CDP 验收（quickstart V1~V5） | PASS（按计划） |
| II. 对象与封装 | 领域对象建模；边界清晰；不共享可变全局状态 | 后端新增 `jobs/catalog.py`（注册表对象）与 `jobs/reconcile.py`（启动对账，独立于 JobManager 的活任务职责）；前端以 Pinia 单例 store 收敛订阅——替换"每组件各自 EventSource"的分散状态（现状恰是本原则反对的共享可变分散态）；视图只依赖本地 API 契约 | PASS（按计划） |
| III. 约定大于配置 | 契约同步；零配置发现；默认开箱即用 | 重跑 starter 由域路由模块注册（新增可重跑类型=注册一行）；任务类型能力目录单一事实源（catalog）；`/jobs` 过滤与 rerun 端点契约增量入本特性 contracts/ 并同步 001 `local-api.md`；无迁移、无新配置项 | PASS（按计划） |
| IV. 技术栈限定 | 既定栈；依赖审查 | 零新增第三方依赖（Element Plus 全量引入已含所需组件；SSE 用原生 EventSource）；无重量级捆绑 | PASS（按计划） |
| V. 密钥零入库 | 凭证只运行时提供、加密、脱敏 | 本特性不触碰凭证路径；任务台账/进度/日志沿用既有脱敏口径（日志正文由各任务既有实现产出，本特性只做转发展示） | PASS（按计划） |
| 开发工作流 | speckit 全流程；逐任务提交；质量门 | 本计划即流程产物；tasks.md 生成后逐任务提交（任务+测试同提交）；合并前测试全绿/契约同步/清单无未决项 | PASS（按计划） |

**Phase 1 设计后复核**：research.md / data-model.md / contracts 未引入新违反项——关键复核点：① 新增端点仅过滤参数与重跑动作，无凭证面；② 对账/重跑均为**用户主动触发**（启动对账只改状态，不重放外呼）；③ `interrupted` 仅值域扩展，无迁移风险（旧版读到该值按未知状态呈现，向后兼容）；④ 测试锁定点矩阵（契约 §6）覆盖全部 FR。**复核结论：PASS**。

## Complexity Tracking

> 无违宪项。本节不适用（若实现期出现必须的例外，按宪法 Governance 记录于此）。

## Project Structure

### Documentation (this feature)

```text
specs/005-task-center/
├── plan.md              # 本文件（/speckit-plan 输出）
├── research.md          # Phase 0 输出：八项关键决策与依据
├── data-model.md        # Phase 1 输出：状态机、任务类型目录、store 形状
├── quickstart.md        # Phase 1 输出：验证指南（V1~V5）
├── contracts/
│   └── task-center-contract.md   # 本特性契约增量（过滤/重跑/状态值域/SSE 映射/呈现约定）
└── tasks.md             # Phase 2 输出（/speckit-tasks 生成，不在本阶段）
```

### Source Code (repository root)

```text
backend/
├── src/saler/
│   ├── api/
│   │   ├── main.py                    # create_app：启动对账调用（reconcile_interrupted_jobs）
│   │   ├── serializers.py             # job_to_dict +can_pause/+rerunnable（由 catalog 派生）
│   │   └── routes/
│   │       ├── jobs.py                # status 逗号多值过滤；SSE 终态快照映射修正；POST /jobs/{id}/rerun
│   │       ├── crawl.py               # 启动助手抽取（初次与重跑共用）；run_job 全周期同步 crawl_job 状态；注册 crawl 重跑 starter
│   │       ├── seeds.py               # 抽取回灌启动助手；注册 ingest_harvest 重跑 starter
│   │       └── companies.py           # 抽取导入启动助手；注册 company_import 重跑 starter
│   └── jobs/
│       ├── engine.py                  # TERMINAL_STATUSES + "interrupted"
│       ├── reconcile.py               # 新增：reconcile_interrupted_jobs（job 非终态→interrupted；联动 crawl_job）
│       └── catalog.py                 # 新增：任务类型目录（pausable/rerunnable 全量 15 型）+ 重跑 starter 注册表
└── tests/
    ├── unit/
    │   ├── test_jobs_reconcile.py     # 新增：对账（running/queued→interrupted、终态不动、crawl_job 联动、finished_at）
    │   └── test_jobs_catalog.py       # 新增：目录完整性（15 型全声明；rerunnable⇒starter 已注册；pausable 白名单）
    ├── contract/
    │   └── test_jobs_api.py           # 新增：多状态过滤（含 422）、rerun（成功/非注册类型 409/非终态 409/completed 拒绝）、SSE 快照终态映射
    └── integration/
        └── test_us2_crawl_flow.py     # 扩展：crawl_job 状态全周期一致（completed/failed/cancelled/interrupted）

frontend/
├── src/
│   ├── stores/jobCenter.ts            # 新增：全局任务中心 store（活跃/最近/日志/订阅/通知/控制/重跑/刷新恢复）
│   ├── api/
│   │   ├── jobs.ts                    # TERMINAL_STATUSES +interrupted；watchJob 收敛为 store.waitFor
│   │   └── types.ts                   # JobPayload +can_pause/+rerunnable
│   ├── composables/useJobEvents.ts    # 保留为 store 内部订阅实现（组件级用法移除）
│   ├── constants.ts                   # JOB_TYPE_ROUTES（job_type→跳转路由，未知回退任务中心）
│   ├── components/common/
│   │   ├── TaskCenter.vue             # 新增：顶栏入口（徽标+转圈）+ 任务抽屉（活跃/最近两组/操作/耗时）
│   │   └── StatusTag.vue              # +interrupted 配色
│   ├── i18n/zh-CN.ts                  # +status.interrupted 等文案
│   ├── layouts/MainLayout.vue         # 挂载 TaskCenter
│   ├── views/
│   │   ├── leads/CrawlJobs.vue        # 监控卡片改读 store；进入自动选中活跃任务；启动后登记；同类活跃提示
│   │   ├── campaigns/CampaignMonitor.vue  # 同上（含发送控制）
│   │   ├── campaigns/RecordTable.vue  # 重试发送走 store（完成提示经通知）
│   │   ├── seeds/AiExpandDialog.vue   # 转后台（关闭不中断提示）+ 重开呈现进行中态
│   │   ├── seeds/SeedList.vue         # 种子翻译对话框：转后台 + 重开呈现进行中态
│   │   ├── seeds/ImportExport.vue     # 检索扩充/回灌走 store（离页不中断）+ 已中断重跑入口
│   │   ├── leads/ImportExport.vue     # 名单导入走 store（离页不中断）+ 已中断重跑入口
│   │   ├── content/AiContentDialog.vue# 起草/多语言：转后台 + 重开呈现
│   │   └── settings/
│   │       ├── Backup.vue             # 备份/恢复/导出走 store（离页不中断、终态通知）
│   │       └── General.vue            # 数据目录迁移走 store
└── tests/
    ├── job-center-store.test.ts       # 新增：订阅合并/通知去重/刷新恢复/控制/重跑
    ├── task-center.test.ts            # 新增：徽标计数/抽屉分组/耗时/跳转/空态
    └── dialog-background.test.ts      # 新增：对话框重开呈现进行中态（各入口代表性用例）
```

**Structure Decision**: 沿用 001 三段式布局，纯增量与局部重构。后端三处新文件均落在既有 `jobs/` 包（对账、目录与注册表与 JobManager 共置，职责分离：管理器管"活任务"，对账管"死任务"）；重跑 starter 由各域路由模块注册（与 providers registry 同款零配置惯用法）；前端新增唯一全局 store 作为任务状态单一事实源，视图层全部改为消费方——消除"每视图各自 EventSource"的分散订阅（FR-008 同源一致的实现基础）。

## Phase 0 / Phase 1 关键决策摘要

（完整决策与依据见 [research.md](research.md)；数据形状与状态机见 [data-model.md](data-model.md)；接口增量见 [contracts/task-center-contract.md](contracts/task-center-contract.md)）

- **每任务既有 SSE + store 聚合（非全局聚合流）**：活跃任务通常 1~2 个，per-job SSE 已具备"快照先行 + 自动重连 + 终态即断"的完整语义，store 内聚后页内监控零改动地获得同一数据源；新增全局聚合流收益不抵后端改动面（R1）。
- **`interrupted` 是"对账产物"而非运行时状态**：只在启动对账时写入（区别于 failed/cancelled 的运行时来源）；纳入 TERMINAL_STATUSES，SSE 快照按 `error(code=interrupted)` 呈现；已中断不发瞬时通知（用户不在场，由任务中心常驻呈现）（R2）。
- **重跑 = 注册表 + 通用端点**：`POST /jobs/{id}/rerun` 依据 `jobs/catalog.py` 的 starter 注册表按类型分发；仅"挖掘/回灌/导入"三类具备断点安全语义可注册；守卫：原始任务必须为终态且非 completed（对外调用不自动重放；completed 重跑入口不提供，避免重复抓取误用）（R3）。
- **多状态过滤一次请求**：`GET /jobs?status=running,paused,queued`（逗号列表，未知值 422）；"最近终态"= 终态四值 + `page_size=20`（默认 id 倒序），24 小时窗口客户端过滤（R4）。
- **对话框"重开呈现进行中态"以 job_type 为粒度**：store 暴露 `activeJobOfType(job_type)`；对话框 open 时命中即渲染进度视图（关闭=转入后台，前后端均无取消语义）——同型并发在对话框入口不再可能（页面按钮类入口保留并提示）（R5）。
- **通知去重与会话语义**：仅在"本会话观察到 活跃→终态 迁移"时发 `ElNotification`（点击跳转）；用户主动取消经 control 路径打标记不通知；页面刷新后对既定终态不补发（R6）。
- **SSE 终态快照映射修正**：现状 cancelled/interrupted 会被快照分支误映射为 `done`（前端误当完成）；本特性按终态分派 `done` 或 `error(code∈{job_failed,cancelled,interrupted})`，前端据 code 落状态（R7）。
- **任务能力单一事实源**：`jobs/catalog.py` 静态声明 15 型任务的 `pausable`/`rerunnable`（pausable 与各引擎 checkpoint 实况一一对应；目录测试断言 rerunnable⇒starter 已注册，防漂移）；`job_to_dict` 输出两字段，前端据此渲染控制按钮（R8）。
