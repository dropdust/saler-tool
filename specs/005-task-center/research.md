# Phase 0 Research: 统一任务中心与任务后台化

**Feature**: `005-task-center` | **Date**: 2026-10-14 | 上游：[spec.md](spec.md) / [plan.md](plan.md)

技术上下文的未知项均在编写本文件前解析完毕（**无遗留 NEEDS CLARIFICATION**）。调研渠道：① 现状代码侦察（backend `jobs/`/`api/routes`、frontend 订阅与对话框实现、001 契约）；② 001/004 既有交付的语义与惯用法（JobManager、SSE 快照先行、registry 零配置注册、CDP 验收配方）。**声明**：任务类型与暂停能力的对应关系以当前各引擎 `ctx.checkpoint()` 实况为准（本调研截至 2026-10-14），目录测试锁定防漂移。

---

## R1 全局状态机制：单例 store + 复用 per-job SSE（不新增全局聚合流）

**Decision**: 前端新增 Pinia 单例 store（`stores/jobCenter.ts`）作为唯一订阅方：应用启动拉取"活跃 + 最近终态"两个列表；对每个活跃任务用既有 `GET /jobs/{id}/events`（SSE，快照先行）建立订阅；组件（顶栏抽屉、挖掘任务页、计划监控页）一律从 store 读取，不再各自建连。刷新/重进的"自动恢复"= 重新初始化时的列表拉取 + 自动重订阅（服务端快照先行保证进度不缺失，EventSource 原生重连兜底断线）。

**Rationale**: per-job SSE 已具备本特性所需的全部语义（订阅即快照、终态即断、自动重连），后端零改动即可复用；活跃任务单用户场景通常 1~2 个（星标约束 ≤3），连接数远低于浏览器对同源连接的限制；页内监控收敛到 store 后，FR-008"同源一致"成为结构性保证而非纪律要求。

**Alternatives considered**:
- **全局聚合 SSE（`GET /jobs/events` 推所有任务事件）**：前端更简单，但要新增服务端聚合订阅/多路复用与生命周期管理（含订阅建立前的任务识别、断线补漏），改动面大且与既有 EventBus 语义（按 job_id 订阅）不一致——否决；若未来任务量级上升再评估。
- **纯轮询**：无需 SSE，但丢失秒级实时性，与既有 `useJobEvents` 能力重复建设——否决。
- **每组件独立订阅（现状）**：同一任务 N 份连接、状态多处副本（正是 FR-008 要消除的矛盾来源）——否决。

## R2 「已中断」状态与启动对账：`create_app` 内一次性对账，`interrupted` 为终态

**Decision**: 新增 `jobs/reconcile.py::reconcile_interrupted_jobs(session_factory) -> dict`，在 `create_app(...)`（`api/main.py`）装配 `job_manager` 之后调用一次：将**全部非终态**（queued/running/paused）的 `job` 行置为 `interrupted`、写 `finished_at`；对 `ref_type='crawl_job'` 的行联动把对应 `crawl_job.status` 同置 `interrupted`。`interrupted` 纳入 `TERMINAL_STATUSES`（engine.py），SSE 对其直接走"快照 + 终态事件"路径即断。

**Rationale**: 任务协程只存在于服务进程事件循环内，进程退出即死；对账把"显示运行中但无执行者"的幽灵状态在**应用可用之前**就消灭（FR-017/020 的地基）。放 `create_app` 而非桌面壳 `_build_app`：dev（`api/dev.py`）、桌面、`--server`、测试四种入口的 `create_app` 是唯一公共汇聚点，一处生效全部入口。职责上对账是"死任务的清理"，与 JobManager（活任务执行）分离，且仅启动时执行一次，不引入常驻负担。

**Alternatives considered**:
- 桌面壳 `_build_app`（与 `run_maintenance` 并列）：dev/uvicorn 直启不经过它，会漏入口——否决。
- 惰性对账（查询时发现"running 但无任务"再标）：判定需要引入"活跃任务内存台账"比对，读路径带写副作用，复杂且竞态多——否决。
- 自动重跑中断任务：违宪（对外调用必须用户主动触发）——否决；提供手动重跑入口（R3）。

## R3 「重新运行」机制：类型目录 + starter 注册表 + 通用端点

**Decision**: `jobs/catalog.py` 维护重跑 starter 注册表（`register_starter(job_type, fn)` / `get_starter(job_type)`）；域路由模块在 import 时注册：
- `crawl`（`routes/crawl.py`）：starter 从原 `CrawlJob.scope/config` 复原，创建**新** CrawlJob + 新 Job（沿同一 run 工厂函数）；
- `ingest_harvest`（`routes/seeds.py`）、`company_import`（`routes/companies.py`）：starter 以原 `Job.params`（请求体快照）重建请求对象，复用抽取出的启动助手。

通用端点 `POST /jobs/{id}/rerun`（`routes/jobs.py`）：查 starter → 无注册 409 `not_rerunnable`；原任务非终态 409 `not_terminal`；原任务 `completed` 409 `already_completed`（不提供完成件重跑入口，避免重复抓取/重复写入的误用）；成功返回 `{job_id, ...starter 附加项}`（crawl 附 `crawl_job_id`）。

**Rationale**: 与仓库既有 registry 惯用法（provider manifest、search presets）同构，"新增可重跑类型 = 注册一行"；starter 与初次启动路径共用助手函数，保证重跑与首次启动行为完全一致（断点语义由各引擎的库内状态天然承接：挖掘按 pending 域继续、回灌按去重键跳过、导入按唯一约束跳过）。守卫拒绝 `completed` 重跑的对外调用面——重跑是"修复中断/失败"，不是"重放"，符合"对外调用由用户主动触发且**可见可控**"。

**Alternatives considered**:
- 每域各写重跑端点：契约面 ×3，前端还要按类型拼路径——否决；
- 纯前端预填对话框（用户重新点启动）：回灌/导入的任务参数在服务端（上传载荷已随 params 落库），前端无法复原——不能覆盖 FR-018 的"回灌、导入等"——否决；
- 允许 completed 重跑：把"重跑"变成"重放"，重复抓取/重复写入风险与合规面俱增——否决。

## R4 `/jobs` 多状态过滤与"最近终态"窗口

**Decision**: `GET /jobs` 的 `status` 参数支持逗号列表（`status=running,paused,queued`），逐值对照已知状态集合校验，未知值 422；任务中心初始化 = 两个请求：① 活跃三态（全量，无分页压力）；② 终态四值（completed/failed/cancelled/interrupted）+ `page_size=20`（默认 id 倒序），**24 小时窗口由前端按 `finished_at` 过滤**。

**Rationale**: 保持单一端点与既有分页语义，前端两个请求即可完整初始化；24h 窗口是展示策略（spec 默认窗口"可微调、不构成契约"），放前端避免服务端引入时间过滤参数的表达与测试面。

**Alternatives considered**:
- 重复 query 参数（`?status=a&status=b`）：FastAPI 支持但在既有单值语义上引入双形态——否决；
- 新增 `/jobs/active`、`/jobs/recent` 便利端点：冗余面——否决；
- 服务端 `since` 时间过滤：契约变重，收益与前端过滤等——否决。

## R5 对话框「重开呈现进行中态」：以 job_type 为粒度的 store 查询

**Decision**: store 暴露 `activeJobOfType(job_type: string): JobPayload | null`（活跃集合中取该类型最新一条）；4 个对话框（AI 扩充、种子翻译、内容起草、主题级多语言）在 `open()` 时判定：命中则渲染**进行中视图**（状态标签 + 进度/阶段 + 日志尾部 + 「转入后台」（即关闭）+ 「取消任务」），未命中渲染既有表单。关闭对话框（含 X/ESC/点击遮罩）统一语义 = 转入后台：任务继续，关闭前在运行视图中给出"关闭不会中断任务，进度可在任务中心查看"的常驻提示。

**Rationale**: 以 job_type 为粒度而非"对话框实例 id"：对话框是无状态视图，服务端 Job 是唯一事实源；同型任务在单用户场景视为同一工作流（AI 扩充不会两批并行操作；回灌/导入同型并行亦无意义），命中即呈现进行中态使"误重复启动"在结构上不可能（表单根本不出现）。页面按钮类入口（启动挖掘、AI 翻译、重试发送）无"重开"概念，改为启动前检测同型活跃任务 → 明确提示 + 「查看任务中心」入口（用户确认后仍可启动，保留自由）。

**Alternatives considered**:
- 前端持久化"对话框会话→job_id"映射（localStorage）：多一份状态副本、跨刷新一致性成本高——否决；
- 运行中禁止关闭对话框：违反 FR-009/FR-013 且体验更差——否决。

## R6 终态通知：store 观察迁移 + 一次语义 + 取消不打搅

**Decision**: store 对**本会话订阅中的活跃任务**，在收到终态事件（done / error）且状态由非终态迁移为终态时，发一次 `ElNotification`（标题=任务名，正文=结果摘要或失败原因；`onClick` → 按 JOB_TYPE_ROUTES 跳转）。去重：内存 `notified` 集合按 job id；用户主动取消（store.control('cancel') 路径）先登记 id 抑制通知；刷新后对"初始化时即终态"的任务**不补发**（用户不在场时结束的任务由任务中心"最近完成"承载）。

**Rationale**: 通知语义 = "你不在看的时候，事情有了结果"；只在会话内观察到的迁移发通知，天然满足 FR-016"同一任务一次"且刷新/切页不重发。已中断（R2）与主动取消都是"用户已知情或本就不在等"的终态，通知只会构成噪音。

**Alternatives considered**:
- 目标页感知（用户在挖掘任务页时对挖掘任务不通知）：UX 增益小、判定复杂（多任务/多页面）——否决，保持"总是通知一次"的简单确定语义；
- 服务端持久化已通知标记：单机单会话语义下无必要——否决（不落库，内存集合即可）。

## R7 SSE 终态快照映射修正 + 前端状态落位

**Decision**: `routes/jobs.py::job_events` 的终态快照分支按状态分派：`completed → done`；`failed → error(code=job_failed)`；`cancelled → error(code=cancelled)`；`interrupted → error(code=interrupted)`。前端 store（及 `TERMINAL_STATUSES`）据 `code` 落位为对应终态；`api/jobs.ts` 的 `TERMINAL_STATUSES` 增加 `interrupted`。

**Rationale**: 现状快照分支把除 failed 外的终态都发 `done`——订阅一个已取消/已中断任务会被前端当作"完成"（既有缺陷，本特性把它变为必现路径：任务中心/刷新恢复会主动订阅/补齐终态）。修正在服务端单点完成，契约写死映射表。

**Alternatives considered**:
- 新增独立事件名（`interrupted`）替代 error：与既有三事件（progress/log/done/error）模型相比引入新事件类型扩散前端分支——否决，用 `error.code` 区分终态原因（与既有 `cancelled` 先例一致）。

## R8 任务能力目录（pausable/rerunnable）与耗时呈现

**Decision**: `jobs/catalog.py` 静态声明全部 15 型任务元数据（`pausable`、`rerunnable`）。`pausable` 按各引擎 `ctx.checkpoint()` 实况填入：**可暂停** = crawl、campaign_send、seed_discover、ai_seed_expand、ai_seed_translate、ai_term_translate、ai_content_draft、ai_content_translate；**仅取消** = ingest_harvest、company_import、seed_validate、backup、restore、export_all、data_dir_move。`rerunnable` = crawl、ingest_harvest、company_import（与 R3 starter 注册一致，目录测试断言防漂移）。`job_to_dict` 输出 `can_pause`/`rerunnable` 两字段（由目录派生）；前端控制按钮据此渲染（暂停/恢复仅当 `can_pause`；重跑按钮仅当 `rerunnable` 且终态非 completed）。抽屉内"已耗时" = 本地每秒 tick 的 `now − started_at`（完成后的显示 `finished_at − started_at`）；进度呈现：`progress` 含 total 类计数 → 百分比进度条 + 阶段文案，否则 indeterminate + 阶段文案（沿用 CrawlJobs 既有 progressPercent/progressText 口径，抽为 store 级 helper）。

**Rationale**: "状态真实"不止初始状态——若对不支持协作点的任务亮出"暂停"，点击后状态显示 paused 而任务实际仍在跑（JobManager.pause 只改状态位）。能力必须来自单一事实源并杜绝漂移（目录测试）。耗时/进度的两种形态复用既有页面已验证的呈现口径，反哺到全局组件保持全应用一致。

**Alternatives considered**:
- 前端硬编码能力表：与后端真实能力漂移（新任务类型加入时前端静默过期）——否决；
- 为所有任务补齐 checkpoint 使全部可暂停：扩面到 7 个任务实现（备份/导出/迁移等短任务收益低），超出本特性范围——否决（目录可后续一行放开）。
