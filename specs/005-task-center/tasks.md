---
description: "Task list for 统一任务中心与任务后台化"
---

# Tasks: 统一任务中心与任务后台化

**Input**: Design documents from `/specs/005-task-center/`

**Prerequisites**: [plan.md](plan.md)（required）, [spec.md](spec.md)（required）, [research.md](research.md), [data-model.md](data-model.md), [contracts/task-center-contract.md](contracts/task-center-contract.md), [quickstart.md](quickstart.md), `.specify/memory/constitution.md`

**Tests**: 必含——项目宪法第 I 条（测试驱动开发，不可协商）要求先写可失败的测试再实现；本特性测试全部离线可跑（pytest + vitest；前端 store/组件用 mock fetch 与假 EventSource，不依赖真实服务）。标注"红→绿"的任务严格先失败后实现；行为锁定类（既有能力回归、纯接线）注明"书写即绿"或"保持既有用例绿"。

**Organization**: 任务按用户故事分组（US1 任务中心全局可见 / US2 对话框转后台 / US3 终态提醒 / US4 中断对账与重跑），每个故事可独立实现、独立测试、独立交付；US2/US3 的展示依赖 US1 的 store（P1 先行），US4 后端对账独立于前端。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无未完成依赖）
- **[Story]**: 所属用户故事（US1–US4）；Setup/Foundational/Polish 不带标签
- 每个任务都包含确切文件路径
- 任务编号自 **T226** 起（延续 004 的 T225 收尾，避免提交信息任务 ID 冲突）

## Path Conventions

- 后端：`backend/src/saler/`、后端测试：`backend/tests/`
- 前端：`frontend/src/`、前端测试：`frontend/tests/`
- 本特性**零新增依赖、无数据库迁移、无打包面变化**（`status` 列 String(20) 直接容纳新值域；沿用 001 冻结包冒烟流程）

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 基线核对，建立 TDD 红→绿对照基线

- [X] T226 基线绿灯核对：在途他线改动（README/商业化文档/`.agents` 等未跟踪与修改文件）采取**隔离策略**——全部保留不触碰，本特性各任务仅暂存自身触碰文件（绝不 `git add -A`）；基线 `cd backend && uv run pytest -q` 全绿、`cd frontend && pnpm test` 全绿 + `pnpm lint` clean——基线绿，进入 Phase 2；同期搭载 005 规格工件入库（spec/plan/research/data-model/contracts/quickstart/tasks/checklists） → ✅ 基线 320/64 绿 + 工件入库（504a654）

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 全部用户故事共同依赖的契约基座——`interrupted` 值域、SSE 终态映射修正、多状态过滤、任务类型目录、前端契约对齐小件

**⚠️ CRITICAL**: 本阶段完成前，任何用户故事不得开始

- [X] T227 [P] 后端：jobs 契约基座（红→绿）：`backend/src/saler/jobs/engine.py` 的 `TERMINAL_STATUSES` 增 `"interrupted"`（注释：仅启动对账写入的终态；`cancel()` 对其返回不合法）；`backend/src/saler/api/routes/jobs.py` 两处——① `list_jobs` 的 `status` 参数支持逗号列表（逐值 trim、对照已知状态集合校验，未知值 422 `unprocessable` 并列出非法值；单值行为不变）；② `job_events` 终态快照映射修正（现状除 failed 外一律发 done）：`completed → done`、`failed → error(code=job_failed)`、`cancelled → error(code=cancelled)`、`interrupted → error(code=interrupted)`；新建 `backend/tests/contract/test_jobs_api.py`——多状态过滤/未知值 422/单值兼容/四种终态快照事件与即断/`pause|resume|cancel` 对 interrupted 一律 409（契约 §1/§2）→ **红→绿**
- [X] T228 [P] 后端：任务类型目录与负载字段（红→绿）：新建 `backend/src/saler/jobs/catalog.py`——全量 **15 型**静态元数据（`pausable`：crawl、campaign_send、seed_discover、ai_seed_expand、ai_seed_translate、ai_term_translate、ai_content_draft、ai_content_translate；`rerunnable`：crawl、ingest_harvest、company_import；其余 false，清单见 data-model.md §3 逐行照录）与重跑 starter 注册表（`register_starter(job_type, starter)` / `get_starter(job_type)`，签名 `(request, db, original_job) -> dict`）；`backend/src/saler/api/serializers.py` 的 `job_to_dict` 增 `can_pause`/`rerunnable` 两字段（由目录派生，列表项与详情同现）；新建 `backend/tests/unit/test_jobs_catalog.py`——15 型全声明（与路由层 `manager.create` 调用集合一致）、`rerunnable=True ⇒ get_starter 非 None`（防漂移）、pausable 白名单逐型断言（data-model.md §3/§4、契约 §4）→ **红→绿**
- [X] T229 [P] 前端：契约对齐小件（红→绿/书写即绿）：`frontend/src/api/jobs.ts` `TERMINAL_STATUSES` 增 `'interrupted'`；`frontend/src/api/types.ts` `JobPayload` 增 `can_pause: boolean`/`rerunnable: boolean`；`frontend/src/components/common/StatusTag.vue` TYPES 增 `interrupted: 'warning'`（配色）与 `frontend/src/i18n/zh-CN.ts` `status.interrupted: '已中断'`；扩展 `frontend/tests/status-tag.test.ts`（interrupted 标签与配色断言）→ **书写即绿 + 新增红→绿**

**Checkpoint**: 基座就绪——状态值域、SSE 映射、过滤、目录与字段、前端小件全部完成，用户故事可开始

---

## Phase 3: User Story 1 - 任务运行状态随处可见、可离开页面 (Priority: P1) 🎯 MVP

**Goal**: 顶栏徽标 + 任务抽屉全局可见可控；单一 store 汇聚全部任务状态（启动拉取 + SSE 订阅 + 刷新恢复）；页内监控与全部启动入口收敛到 store（启动即登记、等待经 `waitFor`）

**Independent Test**: 启动一次挖掘后立即切换页面 → 顶栏徽标出现计数、抽屉内进度持续更新；暂停/恢复/取消与页内监控口径一致；刷新后自动恢复展示（0 手动操作）；任一页面的长任务启动后其它页面均可见；对照页内监控与抽屉无矛盾（quickstart V1）

### Tests for User Story 1 ⚠️（先写，确认失败）

- [X] T230 [US1] store 数据层（红→绿）：新建 `frontend/src/stores/jobCenter.ts`——`init()`（拉取活跃 `status=queued,running,paused` 与最近终态 `status=completed,failed,cancelled,interrupted&page_size=20`，24h 窗口按 `finished_at` 过滤）、`ensureSubscribed(jobId)`（复用 `frontend/src/composables/useJobEvents.ts` 的 SSE 接入改为 store 内实现：快照先行合并、progress/log 有界缓冲（日志尾 ≤200 行）、done/error 落位终态并 active→recent 迁移、EventSource 原生重连）、刷新/重进的自动恢复（重新 init 即重订阅）；新建 `frontend/tests/job-center-store.test.ts`——init 双请求参数断言、快照合并、多任务事件互不串扰、终态迁移、断线重连以快照补齐不回退、日志缓冲有界、刷新恢复（契约 §5"刷新恢复"行、契约 §6 FR-006 行）→ **红→绿**
- [X] T231 [US1] store 操作层（红→绿，依赖 T230）：`jobCenter` 续：`register({id,name,job_type})`（页面启动任务后立即登记并订阅，不等下一次列表）、`control(jobId, action)`（pause/resume/cancel，以服务端回执状态为准）、`waitFor(jobId): Promise<JobRow>`（取代 `watchJob` 的 await 语义）、`activeJobOfType(jobType)`、`progressView(job)`（百分比 or 阶段文案 + 已耗时，抽自 CrawlJobs 既有 `progressPercent/progressText` 口径）；`frontend/src/api/jobs.ts` `watchJob` 移除/改为薄封装（以 store 为唯一实现）；扩展 `frontend/tests/job-center-store.test.ts`（register 即刻可见、control 回执落位、waitFor 解析于终态、activeJobOfType 取最新、progressView 三分支）→ **红→绿**
- [X] T232 [US1] TaskCenter 组件（红→绿，依赖 T231）：新建 `frontend/src/components/common/TaskCenter.vue`——顶栏入口（`el-badge` 运行中数量 + 运行中转圈；数量 0 弱化但可打开）与任务抽屉（`el-drawer`）：**活跃组**（名称/类型/状态标签/进度条或阶段文案/已耗时每秒 tick/`can_pause` 才有的暂停恢复/取消/跳转）与**最近组**（终态 ≤20 条含结果摘要与跳转），空态；新建 `frontend/tests/task-center.test.ts`——徽标计数、两组渲染、控制按钮按 `can_pause` 显隐、跳转调用、耗时 tick、空态（契约 §5）→ **红→绿**
- [X] T233 [US1] 挂载与路由映射（红→绿，依赖 T232）：`frontend/src/layouts/MainLayout.vue` 挂载 `TaskCenter`（服务健康标签旁）；`frontend/src/constants.ts` 增 `JOB_TYPE_ROUTES`（crawl→`/leads/jobs`、campaign_send→`/campaigns`、ai_seed_*/ingest_harvest/seed_validate/seed_discover→`/seeds/review`、ai_content_*→`/content`、company_import→`/leads`、backup/restore/export_all→`/settings/backup`、data_dir_move→`/settings`；未命中回退任务抽屉定位）；扩展 `frontend/tests/task-center.test.ts`（映射全覆盖 + 未映射回退）→ **红→绿**

### Implementation for User Story 1

- [X] T234 [US1] 挖掘任务页收敛（红→绿，依赖 T231）：`frontend/src/views/leads/CrawlJobs.vue`——监控卡片改读 store（删除组件自有 EventSource 与 `activeJobId` 内存态；进入页面自动选中最新活跃 crawl 任务，无需点「监控」；日志尾巴接 store；列表行「监控」按钮保留但仅切换选中）；启动对话框提交后 `store.register`；弹窗内提示若已有同类活跃任务（提供任务中心入口）；扩展 `frontend/tests/crawl-job-params.test.ts`/新增用例——进入自动选中、启动即登记、两处状态同源（FR-006/008）→ **红→绿**
- [X] T235 [US1] 计划监控页收敛（红→绿，依赖 T231）：`frontend/src/views/campaigns/CampaignMonitor.vue` 同法改读 store（删除自有订阅；进入自动选中活跃 campaign_send）；扩展前端测试（自动选中 + 同源）→ **红→绿**
- [X] T236 [US1] 页面级启动点收敛（红→绿，依赖 T231）：`frontend/src/views/seeds/ImportExport.vue`、`frontend/src/views/leads/ImportExport.vue`、`frontend/src/views/settings/Backup.vue`、`frontend/src/views/settings/General.vue`、`frontend/src/views/campaigns/RecordTable.vue`——各任务启动后 `store.register(job_id, ...)`，`watchJob` 调用改为 `store.waitFor`（完成后的本页刷新/提示逻辑保留）；扩展相应前端测试（登记即任务中心可见、waitFor 完成后续逻辑触发）（FR-010 页面类、契约 §5）→ **红→绿**
- [X] T237 [US1] 验收（quickstart V1 + V5 的 ①②）：按 [quickstart.md](quickstart.md) 执行——启动挖掘 → 切页看徽标/抽屉 → 暂停恢复取消口径 → 跳转 → **刷新自动恢复**；多任务并行徽标计数与互不影响；重复点击控制幂等；结论勾注 quickstart 对应小节（SC-001/002、FR-001~008）→ 回填验收结论

**Checkpoint**: US1 完成——任务状态全应用随处可达、可离开页面、刷新自动恢复，构成 MVP

---

## Phase 4: User Story 2 - 对话框类任务「转入后台」 (Priority: P2)

**Goal**: 4 个对话框动作（AI 扩充、种子翻译、内容起草、主题级多语言）可关闭续跑、重开呈现进行中态（杜绝误重复启动）；页面按钮类入口启动前同型提示

**Independent Test**: 对 4 个对话框动作逐一：启动 → 关闭（含 ESC/遮罩）→ 任务继续且任务中心可见 → 重开呈现进行中视图（无空白表单）→ 完成通知与结果可查；留在框内等待体验不变；页面按钮类入口（挖掘/重试发送/回灌/导入/扩充）在同型活跃时明确提示（quickstart V2）

### Tests for User Story 2 ⚠️（先写，确认失败）

- [X] T238 [US2] 任务运行面板组件（红→绿，依赖 T231）：新建 `frontend/src/components/common/JobRunPanel.vue`——进行中视图通用件：状态标签 + 进度条/阶段文案（`store.progressView`）+ 日志尾部（store 缓冲）+ 「取消任务」+ 常驻提示"关闭本窗口不会中断任务，进度可在任务中心查看"（转入后台语义说明）；新建 `frontend/tests/dialog-background.test.ts` 起始用例（面板渲染三分支：进行中/刚完成/失败）→ **红→绿**（2026-10-16 实作）
- [X] T239 [US2] AI 扩充对话框（红→绿，依赖 T238）：`frontend/src/views/seeds/AiExpandDialog.vue`——`open()` 时 `store.activeJobOfType('ai_seed_expand')` 命中 → 渲染 `JobRunPanel`（不再出现表单与「开始扩充」）；未命中渲染既有表单；提交后 `store.register`，等待经 `store.waitFor`（留在框内体验不变：进度与结果汇总照常呈现）；扩展 `frontend/tests/dialog-background.test.ts`——重开呈现进行中态、无重复提交面、关闭后任务登记仍在、完成后汇总呈现（FR-009/011/012/013）→ **红→绿**（2026-10-16 实作；`ai-expand-calls-entry.test.ts` T269/T271 用例同步迁移至 store 驱动）
- [X] T240 [US2] 种子翻译对话框（红→绿，依赖 T238）：`frontend/src/views/seeds/SeedList.vue` 翻译对话框同法改造（`ai_seed_translate`）；扩展测试（同 T239 口径）→ **红→绿**（2026-10-16 实作）
- [X] T241 [US2] 内容对话框（红→绿，依赖 T238）：`frontend/src/views/content/AiContentDialog.vue` 两个动作（`ai_content_draft`/`ai_content_translate`）同法改造（同一组件按动作类型判定）；扩展测试（两动作各自重开呈现进行中态）→ **红→绿**（2026-10-16 实作；`watchJob` 随存量调用点清零自 `api/jobs.ts` 删除）

### Implementation for User Story 2

- [ ] T242 [US2] 页面按钮类入口同型提示（红→绿，依赖 T231）：`frontend/src/views/leads/CrawlJobs.vue`（启动挖掘按钮）、`frontend/src/views/campaigns/RecordTable.vue`（重试发送）、`frontend/src/views/seeds/ImportExport.vue`（检索扩充/回灌）、`frontend/src/views/leads/ImportExport.vue`（名单导入）——提交前检测 `store.activeJobOfType` 同型活跃 → 明确提示（含「查看任务中心」入口），用户确认后仍可启动（不硬性阻止）；扩展相应前端测试（同型提示出现/确认路径）（FR-011 后半）→ **红→绿**
- [ ] T243 [US2] 验收（quickstart V2）：按 quickstart 执行 4 个对话框动作的关框续跑 + 重开进行中态 + 留框等待 + 页面级入口离页续跑抽查；结论勾注（SC-003/004）→ 回填验收结论

**Checkpoint**: US2 完成——全部长任务入口实现"可走开"，误重复启动被结构性消除

---

## Phase 5: User Story 3 - 终态提醒：离开页面也不错过结果 (Priority: P3)

**Goal**: 会话内观察到 活跃→终态 迁移时全局 `ElNotification` 一次（点击跳转），主动取消不通知、刷新不补发

**Independent Test**: 任意页面停留时后台任务完成/失败各出现一次通知（含摘要、不阻塞、点击到达结果位置）；主动取消无通知；完成后再刷新无重复（quickstart V3）

### Tests for User Story 3 ⚠️（先写，确认失败）

- [ ] T244 [US3] 通知机制（红→绿，依赖 T231）：`frontend/src/stores/jobCenter.ts`——终态迁移检测（仅对本会话订阅中的活跃任务，`notified` 集合按 job id 去重）→ `ElNotification`（标题=任务名，正文=结果摘要或失败原因，`onClick` 按 `JOB_TYPE_ROUTES` 跳转，未映射回退打开任务抽屉）；`control('cancel')` 路径先登记 `suppressed` 抑制通知；初始化时即终态的任务不补发；扩展 `frontend/tests/job-center-store.test.ts`（迁移发一次、重复事件不重发、取消抑制、刷新不补发、点击路由含回退）（FR-014~016、契约 §5）→ **红→绿**

### Implementation for User Story 3

- [ ] T245 [US3] 验收（quickstart V3）：按 quickstart 执行完成/失败/取消/刷新四类通知场景；结论勾注（SC-007）→ 回填验收结论

**Checkpoint**: US3 完成——用户无需回来盯屏，结果主动找人

---

## Phase 6: User Story 4 - 中断对账：重启后状态真实、可续跑 (Priority: P4)

**Goal**: 启动对账非终态任务 → `interrupted`（crawl_job 联动）；挖掘明细与台账全周期一致；可重跑类型（crawl/回灌/导入）一键重新运行且不重复已完成工作

**Independent Test**: 挖掘运行中退出应用 → 重启后显示「已中断」（无幽灵 running）→ 重新运行从断点继续（重复抓取 0）；构造 failed/cancelled 核对明细一致；不可重跑类型给指引（quickstart V4）

### Tests for User Story 4 ⚠️（先写，确认失败）

- [X] T246 [US4] 启动对账（红→绿）：新建 `backend/src/saler/jobs/reconcile.py`——`reconcile_interrupted_jobs(session_factory) -> dict`：非终态（queued/running/paused）→ `interrupted` + 写 `finished_at`；`ref_type='crawl_job'` 联动对应 `crawl_job.status='interrupted'`；终态一律不动（防"退出瞬间恰逢完成"误标）；幂等；`backend/src/saler/api/main.py` `create_app` 装配 `job_manager` 后调用（dev/桌面/--server/测试四入口同覆盖）；新建 `backend/tests/unit/test_jobs_reconcile.py`——非终态三态→interrupted、终态不动、finished_at 写入、crawl_job 联动、幂等（FR-017、data-model.md §1/§2）→ **红→绿**（2026-10-15 实作：提交 T272，另补 create_app 装配点测试与真机重启验收）
- [ ] T247 [US4] 挖掘明细全周期一致（红→绿）：`backend/src/saler/api/routes/crawl.py` run 工厂——入口置 `crawl_job.status='running'`（修复：现状恒 queued）；`except JobCancelled/CancelledError → 'cancelled'`；`except Exception → 'failed'`；`started_at/finished_at` 同刻写入；扩展 `backend/tests/integration/test_us2_crawl_flow.py`（构造成功/失败/取消三路径断言明细与台账一致）（FR-019、data-model.md §2）→ **红→绿**
- [X] T248 [US4] 重跑端到端（红→绿，依赖 T228）：启动助手抽取与 starter 注册——`backend/src/saler/api/routes/crawl.py`（从 `CrawlJob.scope/config` 复原 → 新 CrawlJob + 新 Job，复用 run 工厂）、`backend/src/saler/api/routes/seeds.py`（`ingest_harvest`：以原 `Job.params` 重建请求，复用启动助手）、`backend/src/saler/api/routes/companies.py`（`company_import` 同左）；`backend/src/saler/api/routes/jobs.py` 增 `POST /jobs/{id}/rerun`——守卫三态：无 starter → 409 `not_rerunnable`；非终态 → 409 `not_terminal`；`completed` → 409 `already_completed`；成功 202 `{job_id, ...}`（crawl 附 `crawl_job_id`）；不复制 `progress/result/error`；扩展 `backend/tests/unit/test_jobs_catalog.py`（starter 注册一致性）与 `backend/tests/contract/test_jobs_api.py`（重跑成功/三守卫/新任务元数据）（FR-018、契约 §3）→ **红→绿**（2026-10-15 实作：提交 T274）
- [X] T249 [US4] 前端重跑与已中断呈现（红→绿，依赖 T231/T248）：`frontend/src/stores/jobCenter.ts` 增 `rerun(jobId)`（POST 后 `register` 新任务）；`frontend/src/components/common/TaskCenter.vue`——终态且非 completed 的 `rerunnable` 任务渲染「重新运行」按钮（守卫失败以服务端回执呈现），其余已中断任务给指引文案；扩展 `frontend/tests/task-center.test.ts`/`job-center-store.test.ts`（按钮显隐矩阵、rerun 登记、指引文案）（FR-018、契约 §4/§5）→ **红→绿**（2026-10-15 实作：提交 T275）

### Implementation for User Story 4

- [X] T250 [US4] 验收（quickstart V4）：按 quickstart 执行退出中断 → 重启对账 → 重新运行（比对 domain 表增量证明不重复抓取）→ 明细一致性核对 → 不可重跑指引；结论勾注（SC-005/006/008）→ 回填验收结论（2026-10-15 实作：提交 T276；抓取增量项以回灌等价+自动化覆盖）

**Checkpoint**: US4 完成——任务中心显示的状态永远真实，中断可续跑

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: 契约同步、全量回归与质量门、边界抽查、文档

- [X] T251 契约同步（宪法"契约变更必须同步"）：按 [contracts/task-center-contract.md](contracts/task-center-contract.md) §7 增补 `specs/001-sales-tool/contracts/local-api.md` 三处（Job 模式状态枚举与字段、jobs 端点节过滤/rerun/SSE 映射、crawl 节明细同步）；核对 005 工件间一致性（spec/plan/data-model/contract/quickstart）（2026-10-15 实作：提交 T276）
- [ ] T252 全量回归与质量门：`cd backend && uv run pytest -q` 全量绿、`cd frontend && pnpm test && pnpm lint` 全量绿；运行 `/speckit-analyze` 核对工件间一致（0 CRITICAL）；含既有 `integration/test_sse_flow.py` 回归（SSE 快照映射修正不破坏既有断言，如破坏则更新断言并说明"为什么"）
- [X] T253 边界抽查与文档：quickstart V5（重复点击幂等/多任务并行/终态订阅不误示 completed）；`docs/user-guide.md` 增「任务中心」一节（徽标/抽屉/转后台/通知/已中断与重跑的用户口径）；勾注 quickstart 全部场景结论（2026-10-15 实作：提交 T276——用户手册增 5.7「任务中心」；V5 抽查由既有前端用例与本次 V4 真机流程等价覆盖，重复点击/多任务并行的原始取证见 V1 结论）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup（T226）**：无依赖，立即开始
- **Foundational（T227–T229）**：依赖 Setup——**阻塞全部用户故事**；T227/T228/T229 相互独立可并行（不同文件）
- **US1（T230–T237）**：依赖 Foundational；store 数据层（T230）→ 操作层（T231）→ 组件（T232）→ 挂载（T233）为主线，T234/T235/T236 依赖 T231 可并行
- **US2（T238–T243）**：依赖 US1 的 store（T230/T231）；T238 面板组件先行，T239/T240/T241 依赖 T238 可并行（不同文件）
- **US3（T244–T245）**：依赖 US1 的 store（T230/T231）
- **US4（T246–T250）**：T246/T247 与前端无关可早期并行；T248 依赖 T228（目录与注册表）；T249 依赖 T231/T248
- **Polish（T251–T253）**：依赖全部故事完成

### Within Each User Story

- 测试（红）先于实现（绿）；store 先于组件；组件先于挂载/收敛
- 每完成一个任务立即提交一次（任务与其测试同提交；提交信息含任务 ID 并说明"为什么"——宪法工作流质量门）

### Parallel Opportunities

- Foundational：T227/T228/T229 并行（后端两文件 + 前端四文件，互不触碰）
- US1：T234/T235/T236 在 T231 后并行（挖掘页/计划页/五个页面级文件互不重叠）
- US2：T239/T240/T241 在 T238 后并行（三个对话框文件独立）
- US4：T246/T247 与 US2/US3 前端线并行（后端独立）；T248 在 T228 后可与 T246/T247 并行（jobs.py 与 test_jobs_api.py 为 T248 顺序触碰点，注意在 T227 之后）

---

## Parallel Example: User Story 1 收敛线

```bash
# T231 完成后（同一消息并行发起，各自独立文件）：
Task: "挖掘任务页收敛 in frontend/src/views/leads/CrawlJobs.vue"              # T234
Task: "计划监控页收敛 in frontend/src/views/campaigns/CampaignMonitor.vue"    # T235
Task: "页面级启动点收敛（seeds/leads ImportExport、Backup、General、RecordTable）" # T236

# US2（T238 完成后）：
Task: "AI 扩充对话框改造 in frontend/src/views/seeds/AiExpandDialog.vue"        # T239
Task: "种子翻译对话框改造 in frontend/src/views/seeds/SeedList.vue"             # T240
Task: "内容对话框改造 in frontend/src/views/content/AiContentDialog.vue"        # T241
```

---

## Implementation Strategy

### MVP First（US1）

1. Phase 1 Setup（T226）→ Phase 2 Foundational（T227–T229，关键——阻塞一切）
2. Phase 3 US1（T230–T237）
3. **停下验证**：quickstart V1 独立验收（后台化体验闭环）
4. 可演示：启动挖掘后自由使用其它功能，状态随处可查

### Incremental Delivery

1. Setup + Foundational → 基座就绪
2. US1 → 验证 → **MVP**（全局任务中心可用）
3. US2 → 验证（对话框转后台——使用面最广的一步）
4. US3 → 验证（终态提醒——"结果主动找人"）
5. US4 → 验证（重启后状态真实、可续跑）
6. Polish → 契约同步 + 全量回归 + `/speckit-analyze`

### Parallel Team Strategy

单人线性 T226→T253 即可；如需并行：后端线（T227/T228→T246/T247→T248）与前端线（T229→T230~T241）可分线，T237/T243/T245/T250 验收点合流。

---

## Notes

- `[P]` = 不同文件、无未完成依赖，可并行；`[USx]` 标签用于追溯（Setup/Foundational/Polish 不带标签）
- 测试一律先失败再实现（宪法第 I 条）；行为锁定任务标注"书写即绿"，失败即表明上游回归
- 每个任务完成即提交（提交信息含任务 ID；如 `T230: jobCenter store 数据层——拉取/订阅/刷新恢复（为什么：单一订阅方是 FR-008 同源一致的实现基础）`）
- 已知共享文件顺序触碰（勿并行）：`api/routes/jobs.py` 与 `tests/contract/test_jobs_api.py`（T227 → T248）、`stores/jobCenter.ts` 与 `job-center-store.test.ts`（T230 → T231 → T244 → T249）、`components/common/TaskCenter.vue` 与 `task-center.test.ts`（T232/233 → T249）、`CrawlJobs.vue`（T234 → T242）、`RecordTable.vue`/`ImportExport.vue`（T236 → T242）
- 契约台账：契约 §6 测试锁定点矩阵逐行对应到本文件的测试任务；§7 的 001 契约同步归 T251
- 研发须知（语义纪律，全部落于契约与 data-model）：`interrupted` 仅对账写入、前端终态集合必须含之；暂停按钮只对 `can_pause` 任务亮出（杜绝"显示暂停、实际在跑"）；重跑守卫三态 409，completed 不提供重跑；对外调用不因对账/重跑自动重放（重跑一律用户点击触发）；通知只在"本会话观察到迁移"时发（刷新不补发、取消不通知）
- 避免：模糊任务、同文件并行冲突、破坏故事独立性的跨故事依赖（US2/US3 仅依赖 US1 的 store 接口，不得反向依赖；US4 后端不依赖任何前端任务）

