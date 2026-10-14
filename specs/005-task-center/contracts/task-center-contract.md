# Phase 1 Contract: 统一任务中心与任务后台化——任务状态、重跑与呈现约定

**Feature**: `005-task-center` | **Date**: 2026-10-14 | 关联：[local-api.md](../../001-sales-tool/contracts/local-api.md)（Job 模式 / jobs 端点节 / crawl 节）——该契约按 §7 同步增补。

本文件定义本特性的五组契约增量：列表过滤扩展、状态值域与 SSE 终态映射修正、重新运行端点、Job 负载字段增量、前端呈现约定。**全部向后兼容**（既有字段/行为不变，仅新增与缺陷修正）。

---

## 1. `GET /api/v1/jobs` 过滤扩展

| 项 | 约定 |
| --- | --- |
| `status` 参数 | 由单值扩展为**单值或逗号列表**：`?status=running,paused,queued`；逐值 trim、去空 |
| 未知状态值 | **422 `unprocessable`**（与既有未知类型校验口径一致）；报错信息列出非法值 |
| 兼容性 | 单值行为与现状完全一致；`job_type` 过滤不变；排序（id 倒序）与分页语义不变 |
| 任务中心初始化 | ① 活跃：`status=queued,running,paused`（全量）；② 最近终态：`status=completed,failed,cancelled,interrupted&page_size=20`，24h 窗口由前端按 `finished_at` 过滤 |

```jsonc
// GET /api/v1/jobs?status=running,paused,queued → 200（节选）
{
  "items": [
    { "id": 42, "job_type": "crawl", "name": "客户线索挖掘", "status": "running",
      "progress": { "phase": "fetch", "fetched_domains": 12, "total_domains": 40 },
      "can_pause": true, "rerunnable": true,
      "ref_type": "crawl_job", "ref_id": 7,
      "created_at": "2026-10-14T09:00:00+00:00", "started_at": "2026-10-14T09:00:01+00:00", "finished_at": null }
  ],
  "total": 1, "page": 1, "page_size": 20
}
```

## 2. 状态值域扩展 `interrupted` 与 SSE 终态快照映射（修正）

**状态值域**：`queued | running | paused | completed | failed | cancelled` **+ `interrupted`（新）**。

| 项 | 约定 |
| --- | --- |
| `interrupted` 语义 | 进程退出遗留的非终态任务，由**启动对账**写入（区别于 `failed`=运行错误、`cancelled`=用户操作）；写 `finished_at` |
| 终态集合 | `TERMINAL_STATUSES = (completed, failed, cancelled, interrupted)`；`POST /jobs/{id}/pause|resume|cancel` 对其一律 409（沿用既有"状态不允许"口径） |
| 快照映射（`GET /jobs/{id}/events`） | **修正既有缺陷**：终态任务订阅时先发快照 `progress`，随后按状态分派终态事件后即断：`completed → done`；`failed → error(code=job_failed)`；`cancelled → error(code=cancelled)`；`interrupted → error(code=interrupted)`（现状：除 failed 外一律发 `done`，已取消/已中断被误示为完成） |
| 运行时事件 | 不变（`done` / `error` 由 JobManager 发布；`cancelled` 的 error.code 沿用现状） |
| 前端落位 | 客户端终态集合必须包含 `interrupted`；`error` 事件按 `code` 映射为 failed / cancelled / interrupted 三态 |

```jsonc
// 订阅一个 interrupted 任务的事件流（快照先行，随即终态即断）
// event: progress  data: {"snapshot": {"id": 41, "status": "interrupted", "can_pause": true, "rerunnable": true, ...}}
// event: error     data: {"code": "interrupted", "message": "应用退出导致任务中断"}
```

## 3. `POST /api/v1/jobs/{id}/rerun`（重新运行）

| 项 | 约定 |
| --- | --- |
| 请求体 | 无 |
| 成功 | **202** `{ "job_id": <新任务 id>, ...starter 附加项 }`（crawl 附 `"crawl_job_id": <新明细 id>`） |
| 分发 | 按原任务 `job_type` 查重跑 starter 注册表（`jobs/catalog.py`）；starter 负责重建执行上下文并登记执行 |
| 守卫 | 无 starter → 409 `not_rerunnable`（附该类型的后续指引语义）；原任务非终态 → 409 `not_terminal`；原任务 `completed` → 409 `already_completed` |
| 新任务元数据 | `name` 沿用原名；`params/ref_type/ref_id` 由 starter 语义决定（crawl 从 `CrawlJob.scope/config` 复原并建新明细行；回灌/导入以原 `params` 重建请求）；**不复制** `progress/result/error` |
| 对外调用声明 | 重跑可能触发检索/写入，属**用户主动操作**；服务端绝不自动重跑（对账只改状态） |

```jsonc
// POST /api/v1/jobs/41/rerun → 202
{ "job_id": 57, "crawl_job_id": 9 }

// POST /api/v1/jobs/42/rerun（对 campaign_send）→ 409
{ "code": "not_rerunnable", "message": "该任务类型不支持重新运行；请前往相关页面检查后重新发起", "details": null }
```

**可重跑类型（本期）**：`crawl`、`ingest_harvest`、`company_import`。其余 12 型不注册（`not_rerunnable`）。

## 4. Job 负载字段增量（列表项与详情一致）

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `can_pause` | bool | 该任务类型支持暂停/恢复（任务类型目录派生）；前端据此渲染暂停/恢复按钮（FR-003） |
| `rerunnable` | bool | 该任务类型可重新运行（任务类型目录派生）；前端仅对"终态且非 completed"的 `rerunnable` 任务渲染重跑按钮（FR-018） |

其余字段语义不变；`can_pause=false` 类型**只提供取消**（忽略暂停请求或前端不渲染），杜绝"状态显示 paused 而任务实际在跑"。

## 5. 前端呈现约定（实现契约）

| 项 | 约定 |
| --- | --- |
| 唯一订阅方 | 全局任务中心 store 是全应用唯一 SSE 订阅方；页内监控（挖掘任务页、计划监控页）与对话框一律读 store——**同一任务全应用一份连接、一处状态**（FR-008） |
| 顶栏入口 | `MainLayout` 常驻入口：运行中数量徽标 + 运行中转圈；数量为 0 时弱化但可打开（FR-001） |
| 任务抽屉 | 两组：**运行中/排队/暂停**（全量，含进度条或阶段文案、已耗时、按 `can_pause` 的暂停/恢复、取消、跳转）；**最近完成**（终态四值 ≤20 条且 24h 内，含结果摘要与跳转）（FR-002/004/005） |
| 刷新恢复 | 应用初始化即拉取活跃并订阅，无需任何手动"监控"操作；SSE 断线由原生重连 + 快照补齐（FR-006/007） |
| 终态通知 | 会话内观察到 活跃→终态 迁移时 `ElNotification` 一次（标题=任务名，正文=结果摘要/失败原因），点击按 `job_type→路由` 映射跳转；未映射类型 → 打开任务抽屉并定位；**主动取消不通知，刷新不补发**（FR-014~016） |
| 对话框转后台 | 进行中视图（状态/进度/阶段/日志尾/取消/关闭）；关闭（含 ESC/遮罩）=转入后台，附"关闭不会中断任务"提示；重开命中 `activeJobOfType(job_type)` → 呈现进行中视图而非表单（FR-009/011/012/013） |
| 页面按钮类入口 | 启动前检测同型活跃任务 → 明确提示 + 「查看任务中心」入口（不硬性阻止，保留用户自由）（FR-011 后半） |
| 已中断呈现 | 状态标签"已中断"；`rerunnable` 类型给「重新运行」按钮（守卫失败以服务端回执呈现），其余给指引文案（FR-018） |
| 耗时 | 进行中本地每秒 tick（`now − started_at`）；终态显示 `finished_at − started_at`（R8） |

## 6. 测试锁定点矩阵（TDD 先行清单）

| 需求 | 锁定测试（先行失败） |
| --- | --- |
| FR-017/019/020（对账） | `unit/test_jobs_reconcile.py`：queued/running/paused→interrupted、终态不动、finished_at 写入、crawl_job 联动、幂等 |
| FR-003/018（能力与重跑） | `unit/test_jobs_catalog.py`：15 型全声明、rerunnable⇒starter 注册、pausable 白名单；`contract/test_jobs_api.py`：rerun 成功/409 三守卫、`can_pause/rerunnable` 字段 |
| FR-001/002/005（列表） | `contract/test_jobs_api.py`：逗号多状态过滤、未知值 422、单值兼容、终态窗口分页 |
| FR-002/007/008（SSE） | `contract/test_jobs_api.py` + `integration/test_sse_flow.py` 扩展：interrupted/cancelled 快照映射为 error(code)、completed → done、终态即断 |
| FR-019（明细一致） | `integration/test_us2_crawl_flow.py` 扩展：run 全周期 crawl_job 状态（running/completed/failed/cancelled） |
| FR-006（刷新恢复） | `frontend/tests/job-center-store.test.ts`：init 订阅活跃、快照合并、断线重连语义、active→recent 迁移 |
| FR-014~016（通知） | 同上前端：迁移发一次、取消抑制、刷新不补发、点击路由映射（含未映射回退） |
| FR-009~013（对话框） | `frontend/tests/dialog-background.test.ts`：重开呈现进行中态、关闭不中断、留框等待保持、按钮类入口同型提示 |
| FR-004/008（抽屉与同源） | `frontend/tests/task-center.test.ts`：徽标计数、两组渲染、控制按钮按 can_pause、跳转、耗时、空态；CrawlJobs/CampaignMonitor 读 store 的一致性用例 |

## 7. 001 契约同步点

按宪法"契约变更必须同步更新契约文件"，本特性落地时同步增补 [001 local-api.md](../../001-sales-tool/contracts/local-api.md)：

1. **Job 模式节（§ 任务模型）**：状态枚举增加 `interrupted`；响应字段增加 `can_pause`/`rerunnable`；
2. **jobs 端点节**：`GET /jobs?status=` 支持逗号列表（422 语义）；新增 `POST /jobs/{id}/rerun`（守卫矩阵）；SSE 终态快照映射修正说明；
3. **crawl 节**：`crawl_job` 状态与台账全周期同步（含 interrupted）说明。
