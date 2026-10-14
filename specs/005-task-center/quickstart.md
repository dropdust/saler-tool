# Quickstart: 统一任务中心与任务后台化

**Feature**: `005-task-center` | **Date**: 2026-10-14

本文件是**验证指南**：如何运行本特性并按用户故事逐条验证。数据形状见 [data-model.md](data-model.md)；接口约定见 [contracts/task-center-contract.md](contracts/task-center-contract.md)；通用环境前提与打包流程沿用 [001 quickstart §1–§3](../001-sales-tool/quickstart.md)。

## 1. 运行与测试

```bash
# 开发形态（后端 + 前端 dev）
cd backend && uv run uvicorn saler.api.dev:app --reload --port 8620
cd frontend && pnpm dev                                   # http://localhost:5173

# 验收形态（构建产物 + 无窗服务 + headless Chrome CDP，沿用本机验收配方）
cd frontend && pnpm build
cd backend && SALER_DATA_DIR=/tmp/saler-accept-005 uv run python -m saler.desktop --server --port 8620

# 自动化测试（离线可跑，无真实外网依赖）
cd backend && uv run pytest tests/unit/test_jobs_reconcile.py tests/unit/test_jobs_catalog.py \
    tests/contract/test_jobs_api.py tests/integration/test_us2_crawl_flow.py tests/integration/test_sse_flow.py
cd frontend && pnpm test && pnpm lint                     # job-center-store / task-center / dialog-background + 全量
```

> **前提声明**：V1~V4 的挖掘/扩充等真实任务需要已配置检索渠道与（或）大模型服务；不可达时用假 Provider/离线样本走自动化层验证（§2 各场景注明）。任务在服务进程内执行——**退出即中断**是设计边界（spec Assumptions），V4 正是验证该边界下的状态真实性。

## 2. 验证场景

### V1 全局任务中心：随处可看、可离开页面（US1 / FR-001~008 / SC-001/002）

前置：配置检索渠道；种子库有 ≥1 条已采纳待执行种子。步骤：① 在「客户线索挖掘」页启动一次挖掘（小参数：并发 2、单站间隔 1s）；② **立即切到其它页面**（种子列表、设置等），核对顶栏徽标计数出现；③ 展开任务抽屉：核对名称/类型/状态/阶段/进度/已耗时持续更新；④ 执行暂停 → 核对抽屉与挖掘页监控卡片两处一致 → 恢复（进度不回退）；⑤ 点击条目跳转核对到达挖掘任务页并自动处于监控态；⑥ **刷新页面**（F5）→ 核对抽屉与页面自动恢复展示该任务，未做任何"监控"操作；⑦ 断开重连验证（可选：kill -HUP 服务或断网恢复）核对进度以快照补齐、不回退。

预期：SC-001（≤5s 徽标可见、零手动监控）、SC-002（刷新后 0 操作恢复）；两处状态无矛盾（FR-008）；暂停/恢复与既有页内控制同口径（FR-003）。

### V2 对话框任务「转入后台」（US2 / FR-009~013 / SC-003/004）

前置：配置大模型服务（不可达时以假 Provider 走 `dialog-background.test.ts` 等价验证）。步骤：对 4 个对话框动作逐一执行——AI 扩充、种子翻译、内容起草、主题级多语言：① 启动任务 → ② **关闭对话框**（含 ESC/遮罩路径抽查）→ 核对任务继续（任务中心可见进度、无中断提示）→ ③ **重开同一对话框** → 核对呈现「进行中」视图（状态/进度/阶段/日志尾/取消），**不出现可再次提交的表单** → ④ 等待完成 → 核对通知到达、点击跳转结果位置、任务中心可见结果摘要；⑤ 抽查一个入口留在框内等待：进度与结果汇总照常呈现（FR-013）。另对页面级入口（回灌、名单导入、备份）抽查：启动后离开页面 → 任务继续、任务中心可见终态。

预期：SC-003（4 对话框动作关框续跑 + 页面级入口离页续跑，结果 100% 可查）、SC-004（重开 100% 进行中态、重复任务 0）；关闭不中断、不丢参数（FR-012）。

### V3 终态提醒：离开页面也不错过（US3 / FR-014~016 / SC-007）

步骤：① 在「种子列表」页停留，后台跑一次挖掘直至完成 → 核对出现含结果摘要的通知、不阻塞操作、点击到达挖掘任务页；② 制造一次失败（如检索渠道全部禁用后启动挖掘 → 任务失败或启动被拒；或断开代理制造抓取全失败）→ 核对失败通知含原因、点击跳转；③ 启动一个长任务后**主动取消** → 核对无"已取消"通知；④ 完成通知出现后刷新页面 → 核对不重复通知。

预期：SC-007（任意页面 100% 可见、重复 0、≤1 次操作到达结果）；主动取消/已中断不通知（FR-016）。

### V4 中断对账与重新运行（US4 / FR-017~020 / SC-005/006/008）

前置：SQLite 直查可用（`sqlite3 <数据目录>/saler.db`）。步骤：① 启动挖掘任务（待执行域较多，确保运行中）→ 在运行中**直接关闭应用**（Ctrl+C 或杀进程）；② 重启应用（同一数据目录）→ 打开任务中心：核对遗留任务显示「已中断」（不是「运行中」），`SELECT status FROM job WHERE status NOT IN (...)` 无幽灵 running；③ 对该已中断任务点「重新运行」→ 核对创建新任务并从断点继续（已完成域不重复抓取：比对重跑前后 `domain` 表 done 计数增量与 fetched 增量）；④ 明细一致性：`SELECT status FROM crawl_job` 与对应 `job.status` 逐条一致（含构造 failed/cancelled 场景）；⑤ 对不可重跑类型（如 backup）的已中断任务核对按钮缺省、指引文案呈现。

预期：SC-005（运行中遗留 0、100% 有后续入口）、SC-006（重跑重复抓取 0）、SC-008（无幽灵任务）；`not_rerunnable/not_terminal/already_completed` 守卫 409 回执正确（契约 §3）。

### V5 边界与一致性抽查（横切）

步骤：① 任务运行中**重复点击**抽屉与页内暂停 → 核对以服务端状态为准（幂等，无异常）；② 同时跑 ≤3 个任务（挖掘 + AI 扩充 + 备份）→ 徽标计数正确、单任务操作互不影响；③ 终态任务订阅（对 completed 与 cancelled 分别开抽屉观察）→ 核对不误示为"完成"（cancelled/interrupted 呈"已取消/已中断"，契约 §2 修正验证）；④ 关闭-重开对话框恰逢任务刚完成 → 核对呈现终态结果汇总而非空白表单（spec 边界情形）。

预期：FR-002/003/008 与契约 §5 全部成立；无任何"运行中"与真实执行不符的呈现（FR-020）。

## 3. 验收记录（实现阶段回填）

各场景验收结论（含证据与截图路径）在实现阶段按 001/004 惯例回填至本文件各场景末尾。
