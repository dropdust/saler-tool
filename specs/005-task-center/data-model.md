# Phase 1 Data Model: 统一任务中心与任务后台化

**Feature**: `005-task-center` | **Date**: 2026-10-14 | 上游：[spec.md](spec.md) / [research.md](research.md)

本特性**不新增实体、不做数据库迁移**：`job` 与 `crawl_job` 表均为**状态值域扩展 + 行为补齐**（`status` 列 `String(20)` 直接容纳 `interrupted`）；新增代码对象两类——后端任务类型目录/重跑注册表（`jobs/catalog.py`）与前端任务中心 store（`stores/jobCenter.ts`，展示态不落库）。

---

## 1. `job.status` 状态机（含 `interrupted`）

```text
                 manager.start()
  queued ────────────────────────▶ running ◀──────┐
    │                                 │  ▲        │ resume()
    │ 启动对账                         │  └────────┤
    │                                 │  pause()  │
    ▼                                 ▼           │
interrupted ◀──启动对账──── paused ────┘           │
    ▲                            │                │
    │                            │ cancel()       │
    │            run 正常结束     │                │
    └── 启动对账 ── completed ◀───┴──▶ cancelled   │
                   （failed/cancelled 亦有运行时路径）
                   running ──异常──▶ failed
```

| 状态 | 写入方 | 语义 |
| --- | --- | --- |
| `queued` | 任务创建（既有） | 已登记未开跑（既有语义不变） |
| `running` | JobManager（既有） | 进程中真实执行 |
| `paused` | JobManager（既有；仅 `can_pause` 类型应出现） | 协作点挂起等待 |
| `completed` / `failed` / `cancelled` | JobManager（既有） | 运行时终态 |
| `interrupted` **（新）** | **仅启动对账**（`jobs/reconcile.py`） | 进程退出遗留的非终态任务；写 `finished_at`；区别于 failed（非运行错误）与 cancelled（非用户操作） |

- `interrupted` ∈ `TERMINAL_STATUSES`（engine.py）：`cancel()` 对其返回不合法；SSE 对其走"快照 + 终态事件"即断。
- 转移规则：**对账仅触碰 `queued/running/paused`**，终态一律不动（防"退出瞬间任务恰逢完成"误标，spec 边界情形）。
- 兼容性：旧版本读到 `interrupted` 按未知状态呈现（String 列无约束），升级后首次启动对历史遗留同样对账（spec Assumptions）。

## 2. `crawl_job.status` 与台账同步（FR-019）

| 场景 | `job`（台账） | `crawl_job`（明细） | 写入点 |
| --- | --- | --- | --- |
| 启动 | running | **running**（修复：现状恒为 queued） | `routes/crawl.py` run 工厂入口 |
| 正常完成 | completed | completed + `stats` | 现状已有，保留 |
| 运行抛错 | failed | **failed**（修复：现状停留 queued） | run 工厂 `except` 分支 |
| 协作式取消 | cancelled | **cancelled** | run 工厂 `except JobCancelled/CancelledError` 分支 |
| 进程退出遗留 | interrupted | **interrupted** | 启动对账（按 `ref_type='crawl_job'` 联动 `ref_id`） |

- 明细与台账的状态取值 1:1 同写；`crawl_job.status` 不引入独立语义。
- `started_at/finished_at` 明细侧同步写（与台账同刻）。

## 3. 任务类型目录（`jobs/catalog.py`，全量 15 型）

| job_type | 展示名（任务创建时已写入 `job.name`，目录不重复承载） | pausable | rerunnable | 依据 |
| --- | --- | --- | --- | --- |
| `crawl` | 客户线索挖掘 | ✔ | ✔ | crawl_engine 协作点；库内 pending 域断点 |
| `campaign_send` | 发送/重试发送 | ✔ | ✘ | sending/engine 逐条协作点；发送不可安全重放 |
| `seed_discover` | 检索扩充图谱 | ✔ | ✘ | seeds/discover 协作点；生成性任务 |
| `ai_seed_expand` | AI 扩充种子 | ✔ | ✘ | seeds/ai 协作点；生成性任务 |
| `ai_seed_translate` | 种子翻译 | ✔ | ✘ | seeds/ai_translate 协作点；生成性任务 |
| `ai_term_translate` | 词表翻译 | ✔ | ✘ | 同上（词表翻译实现） |
| `ai_content_draft` | AI 起草母版 | ✔ | ✘ | content/ai 协作点；生成性任务 |
| `ai_content_translate` | 主题级多语言生成 | ✔ | ✘ | content/ai 协作点；生成性任务 |
| `ingest_harvest` | 回灌收割结果 | ✘ | ✔ | 载荷在 `params`；去重键幂等断点 |
| `company_import` | 导入客户名单 | ✘ | ✔ | 载荷在 `params`；唯一约束幂等断点 |
| `seed_validate` | 外部来源校验 | ✘ | ✘ | 无协作点；失败后到种子页重发起（指引） |
| `backup` | 创建备份 | ✘ | ✘ | 短任务；到备份页重发起（指引） |
| `restore` | 恢复备份 | ✘ | ✘ | 破坏性操作，不提供一键重跑（指引） |
| `export_all` | 全量导出 | ✘ | ✘ | 短任务；到备份页重发起（指引） |
| `data_dir_move` | 迁移数据目录 | ✘ | ✘ | 短任务；到设置页重发起（指引） |

- 目录为 `pausable`/`rerunnable` 的**单一事实源**；`job_to_dict` 由其派生输出（§5）。
- 目录测试断言：15 型全声明（与路由层 `manager.create` 调用集合一致）；`rerunnable=True ⇒ 对应 starter 已注册`（防漂移）。

## 4. 重跑 starter 注册表（`jobs/catalog.py`，与目录同模块）

```text
注册：register_starter(job_type, starter)      # 域路由 import 时调用
查询：get_starter(job_type) -> starter | None
```

- **starter 签名**：`(request: Request, db: Session, original: Job) -> dict`（返回 `{job_id, ...}`，crawl 附 `crawl_job_id`）。
- **注册集合**：`crawl`（crawl.py，从 `CrawlJob.scope/config` 复原 → 新 CrawlJob + 新 Job）、`ingest_harvest`（seeds.py，`params` 重建请求 → 复用启动助手）、`company_import`（companies.py，同左）。
- **守卫（`POST /jobs/{id}/rerun`）**：
  1. 无 starter（类型不可重跑）→ 409 `not_rerunnable`；
  2. 原任务非终态 → 409 `not_terminal`；
  3. 原任务 `completed` → 409 `already_completed`；
  4. 通过 → 新 Job（`name` 沿用原名，`params/ref` 按 starter 语义重建或复制），返回 202。
- 重跑**不复制**原任务的 `progress/result/error`（新任务全新累积；断点来自库内业务状态，不来自台账字段）。

## 5. `Job` JSON 响应增量（`job_to_dict`）

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `can_pause` **（新）** | bool | 该类型支持暂停/恢复（目录派生；暂停按钮渲染依据，FR-003） |
| `rerunnable` **（新）** | bool | 该类型可重新运行（目录派生；重跑按钮渲染依据，FR-018） |

其余字段（`id/job_type/name/status/progress/result/error/ref_type/ref_id/created_at/started_at/finished_at`）语义不变。列表项与详情同一序列化器，两字段同现。

## 6. 前端任务中心 store（展示态，不落库）

```text
useJobCenterStore
├── activeJobs: Map<jobId, JobRow>       # queued/running/paused；初始化拉取 + SSE 合并
├── recentJobs: JobRow[]                 # 终态四值，≤20 条且 finished_at ≥ now-24h
├── logs: Map<jobId, string[]>           # 每任务有界日志尾（≤200 行，progress 事件不计数）
├── subscriptions: Map<jobId, EventSource>
├── notified: Set<jobId>                 # 本会话已通知（FR-016 去重）
├── suppressed: Set<jobId>               # 主动取消抑制通知（FR-016）
└── actions
    ├── init()                           # 拉两列表 + 订阅活跃 + 恢复展示（FR-006）
    ├── ensureSubscribed(jobId)          # 快照先行；终态事件落位并迁移 active→recent
    ├── register(job: {id,name,job_type})# 页面启动任务后立即登记（不等下一次列表）
    ├── control(jobId, action)           # pause/resume/cancel（FR-003；控制后以服务端回执为准）
    ├── rerun(jobId)                     # POST /jobs/{id}/rerun → register 新任务（FR-018）
    ├── activeJobOfType(jobType)         # 对话框重开判定（R5/FR-011）
    ├── waitFor(jobId): Promise<JobRow>  # 取代 watchJob 的 await 语义（完成后再刷新本地视图）
    └── progressView(job)                # 百分比 or 阶段化文案 + 已耗时（R8，抽自 CrawlJobs 口径）
```

- 通知：终态迁移且未在 `suppressed` → `ElNotification`（点击按路由跳转，FR-014/015）。
- 路由映射（`constants.ts`，前端展示配置）：`crawl→/leads/jobs`、`campaign_send→/campaigns`、`ai_seed_expand/ai_seed_translate/ingest_harvest/seed_validate/seed_discover→/seeds/review`（或 `/seeds`）、`ai_content_*→/content`、`company_import→/leads`、`backup/restore/export_all→/settings/backup`、`data_dir_move→/settings`；未命中 → 打开任务抽屉定位该任务（spec 边界情形）。

## 7. 迁移与兼容

- **无 Alembic 迁移**：无列增删；`interrupted` 为既有 String 列新值域。
- 兼容性说明：`/jobs` 响应**只增字段**（`can_pause/rerunnable`）；`status` 参数由单值扩展为单值或逗号列表（单值行为不变）；新增端点纯增量。
- 对账为幂等操作（无遗留非终态时无写入），每次 `create_app` 执行开销为单条 UPDATE 语句级。
