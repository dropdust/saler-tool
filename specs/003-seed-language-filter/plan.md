# Implementation Plan: 种子列表语言筛选

**Branch**: `003-seed-language-filter` | **Date**: 2026-10-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-seed-language-filter/spec.md`

## Summary

在种子列表页筛选栏新增"语言"单选筛选（FR-001~010）：选项覆盖应用统一语言表（LANGS）＋种子库实际取值（含导入/回灌带入的非标准代码与大小写变体，原样显示）；选定后列表仅呈现该语言种子，与既有条件（搜索词/状态/审核/来源/批次/市场）交集组合，总数与分页一致；一步清除恢复全量；查询动作统一将页码复位为第 1 页并显式空态，保证越界不空白。

技术路线（决策依据见 [research.md](research.md)）：后端**已具备** `GET /seeds?lang=` 精确筛选（本期以契约测试正式锁定其行为），仅新增只读端点 `GET /seeds/langs`（DISTINCT 精确取值、升序）支撑选项全覆盖；前端以 `constants.ts` 纯函数 `langFilterOptions(present)` 组装选项（LANGS ∪ 库内取值），SeedList 随每次列表刷新并行拉取取值、查询按钮触发查询并复位页码。**零新增依赖、无 schema/迁移、纯查询无副作用**。

## Technical Context

**Language/Version**: TypeScript 5.6 + Vue 3.5（前端）；Python ≥ 3.12（后端，1 个只读端点）

**Primary Dependencies**: Element Plus 2.8.8 `el-select`（既有组件，clearable 单选，无新增依赖）；FastAPI + SQLAlchemy（既有）

**Storage**: SQLite `seed.lang`（既有列，仅增加读取侧筛选/枚举语义；无 schema 变更、无 alembic 迁移、无数据规范化）

**Testing**: vitest（前端：选项组装纯函数 + SeedList 组件行为）；pytest（后端契约：`/seeds?lang=` 组合筛选与无副作用、`/seeds/langs` 新端点）

**Target Platform**: Windows（WebView2）/ macOS（WKWebView）/ Linux（WebKitGTK）桌面壳；`--server` 浏览器模式同一路径生效

**Project Type**: desktop-app（前后端增量特性）

**Performance Goals**: 10,000 条种子规模下应用/清除语言筛选呈现 ≤ 1s（SC-005）；`/seeds/langs` 为单列 DISTINCT 查询（万行级亚毫秒），随每次列表刷新并行调用 1 次（与既有分页查询同量级）

**Constraints**:
- 筛选为纯查询行为（FR-009）：不写库、不触发对外调用；前端仅发 GET
- 精确匹配语义（按存库原值）：`EN` 与 `en` 为独立选项，不做大小写折叠/去空白（US3 语义）
- 选项口径 = LANGS ∪ 库内实际取值；标准语言恒在选项内（选后可呈空态）
- 零新增依赖；契约与文档同步回 001（宪法"契约变更必须同步"）

**Scale/Scope**: 1 个列表页筛选控件 + 1 个只读端点；前端 1 个纯函数 + 1 个组件（SeedList.vue）+ 2 个测试文件；后端 1 个路由 + 1 个服务函数 + 契约测试增量

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 要求摘要 | 本特性对照 | 结论 |
|---|---|---|---|
| I. 测试驱动开发 | 红→绿→重构；测试分层齐备 | 新端点与前端行为先行落失败测试（pytest 契约：`/seeds/langs` 去重/精确值/空库；vitest：选项纯函数、SeedList 筛选行为、页码复位、空态）；`/seeds?lang=` 在 001 已实现，其契约测试属**行为锁定**（首跑即绿，作为回归网），其余全部红→绿 | PASS（按计划） |
| II. 对象与封装 | 前端组件为边界、只依赖本地 API 契约；后端领域服务 | 选项组装收敛为 `constants.ts` 纯函数（组件仅消费，可独立单测）；后端 `distinct_langs` 归 `core/seeds/service.py`（既有服务对象），路由薄转发；前端仅经 `api` 客户端 | PASS（按计划） |
| III. 约定大于配置 | 契约同步；默认开箱即用；零配置发现 | 交互沿用本页既有"选择→查询"约定；端点命名与声明位置沿用 `/seeds` 族约定（早于 `/{seed_id}`）；契约增量入本特性 contracts/ 并同步 001 local-api.md | PASS（按计划） |
| IV. 技术栈限定 | 不引入新语言/框架；拒绝依赖膨胀 | **零新增依赖**：el-select、FastAPI/SQLAlchemy 均为既有 | PASS |
| V. 密钥零入库 | 密钥不入代码/日志/导出 | 本特性不涉及任何凭证；语言取值为非敏感数据，无脱敏面 | PASS（不适用） |
| 附加约束 | 离线可用；数据主权；中文界面；Web 演进兼容 | 筛选完全离线本地；不触碰任何对外调用路径；文案中文；新端点为通用 REST 加性增量，Web 版可复用 | PASS |
| 工作流质量门 | 逐任务提交；契约同步；关键变更后 analyze | 计划含 001 local-api.md / quickstart 同步任务；实现按 tasks.md 逐任务提交 | PASS（按计划） |

**Phase 1 设计复核**：data-model.md / contracts/seed-lang-filter-contract.md / quickstart.md 与上表逐条对照，无违反项；Complexity Tracking 为空。

## Project Structure

### Documentation (this feature)

```text
specs/003-seed-language-filter/
├── plan.md              # 本文件（/speckit-plan 输出）
├── research.md          # Phase 0 输出：6 项技术决策（选项来源/匹配语义/交互与页码/选项组装/空态/测试）
├── data-model.md        # Phase 1 输出：seed.lang 读取语义 + 语言选项集合派生规则
├── quickstart.md        # Phase 1 输出：验证场景 L1–L5
├── contracts/
│   └── seed-lang-filter-contract.md   # Phase 1 输出：/seeds 查询增量 + /seeds/langs 新端点 + 前端筛选契约
└── tasks.md             # Phase 2 输出（/speckit-tasks 生成，不在本阶段）
```

### Source Code (repository root)

```text
frontend/
├── src/
│   ├── constants.ts                 # 修改：新增 langFilterOptions(present) 纯函数（LANGS ∪ 库内取值组装与标签）
│   └── views/seeds/SeedList.vue     # 修改：筛选栏"语言"选择器（clearable、data-test 钩子）+ 随列表刷新同步加载 /seeds/langs 选项 + 查询复位页码 + 空态文案
└── tests/
    ├── seed-lang-options.test.ts    # 新增：选项组装纯函数（标准/非标准/大小写变体、顺序、标签、去重）
    └── seed-lang-filter.test.ts     # 新增：SeedList 组件（控件与选项、请求携带/清除 lang、页码复位、空态）

backend/
├── src/saler/
│   ├── api/routes/seeds.py          # 修改：新增 GET /seeds/langs（声明于 /{seed_id} 之前）
│   └── core/seeds/service.py        # 修改：distinct_langs(db) 服务函数
└── tests/
    └── contract/test_seeds_api.py   # 修改：新增 TestSeedLangFilter（lang 精确筛选/组合交集/空结果/无副作用；/seeds/langs 去重精确值）

specs/001-sales-tool/                # 契约与文档同步（宪法"契约变更必须同步"）
├── contracts/local-api.md           # 修改：种子知识库表增补 GET /seeds/langs 行；/seeds 行说明补记 lang 筛选（003）
└── quickstart.md                    # 修改：S4 步骤补"在种子列表按语言筛选（003 增量）"
```

**Structure Decision**: 沿用既有前后端单体布局（`backend/` + `frontend/`），无新模块边界。逻辑集中在 4 个既有文件的增量改动（SeedList.vue、constants.ts、seeds.py、service.py）+ 2 个新增测试文件；契约/文档同步回 001 两处。

## Complexity Tracking

> 无宪法违反项，本表为空。
