---
description: "Task list for 种子列表语言筛选"
---

# Tasks: 种子列表语言筛选

**Input**: Design documents from `/specs/003-seed-language-filter/`

**Prerequisites**: [plan.md](plan.md)（required）, [spec.md](spec.md)（required）, [research.md](research.md), [data-model.md](data-model.md), [contracts/seed-lang-filter-contract.md](contracts/seed-lang-filter-contract.md), [quickstart.md](quickstart.md), `.specify/memory/constitution.md`

**Tests**: 必含——项目宪法第 I 条（测试驱动开发，不可协商）要求先写可失败的测试再实现；本特性测试全部离线可跑（vitest + pytest，无需外部服务）。注：`GET /seeds?lang=` 精确筛选在 001 已实现，其契约测试与 US2/US3 中"机制已由构造保证"的用例属**行为锁定/证实性测试**（书写即绿的已注明）；其余新增行为严格红→绿。

**Organization**: 任务按用户故事分组，每个故事可独立实现、独立测试、独立交付。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无未完成依赖）
- **[Story]**: 所属用户故事（US1–US3）
- 每个任务都包含确切文件路径
- 任务编号自 **T177** 起（延续 002 的 T176，避免提交信息任务 ID 冲突）

## Path Conventions

- 后端：`backend/src/saler/`、后端测试：`backend/tests/`
- 前端：`frontend/src/`、前端测试：`frontend/tests/`
- 本特性无打包脚本改动（零新依赖、无打包面变化，沿用 001 冻结包冒烟流程）

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 基线核对，建立 TDD 红→绿对照基线

- [X] T177 基线绿灯核对（现有套件 `backend/tests/`、`frontend/tests/`）：`cd backend && uv run pytest -q` 全绿（213 passed）；`cd frontend && pnpm test && pnpm lint` 通过（vitest 20 passed，lint clean）

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 语言选项基座——库内取值端点（后端）与选项组装纯函数（前端），US1/US3 共同依赖

**⚠️ CRITICAL**: 本阶段完成前，任何用户故事不得开始

- [X] T178 [P] 契约测试（红）：`backend/tests/contract/test_seeds_api.py` 新增 `TestSeedLangsEndpoint`——`GET /api/v1/seeds/langs`：库内 `seed.lang` 去重**精确值**、升序返回（字符串数组）；空库返回 `[]`（contracts/seed-lang-filter-contract.md §2）——2 项确认失败（路径被 `/{seed_id}` 吞掉）
- [X] T179 实现：`backend/src/saler/core/seeds/service.py` 增 `distinct_langs(db)`（`SELECT DISTINCT seed.lang`，滤空值，升序）+ `backend/src/saler/api/routes/seeds.py` 增 `GET /seeds/langs`（**声明于 `/{seed_id}` 之前**，纯读、无参数）→ T178 转绿（后端 215 全过）
- [X] T180 [P] 纯函数单测（红）：`frontend/tests/seed-lang-options.test.ts`——`langFilterOptions(present)`：`LANGS` 全部 17 语言在列且顺序一致、标签为 `中文标签（code）`（如"俄语（ru）"）；不在 `LANGS` 的取值按传入顺序原样追加、标签=code；重复值去重；`present` 含标准码时不重复出现（research R4 / data-model.md 选项集合规则："选项值 = 存库原值；`EN` 与 `en` 为两个独立选项，互不混淆"）——4 项确认失败（模块缺失）
- [X] T181 实现：`frontend/src/constants.ts` 增 `langFilterOptions(present: string[]): Array<{ value: string; label: string }>`（与 `LANGS`/`langLabel` 同族）→ T180 转绿（vitest 24 通过）

**Checkpoint**: 选项基座就绪——后端可枚举库内语言、前端可组装完整选项；用户故事可开始

---

## Phase 3: User Story 1 - 按语言筛选种子列表 (Priority: P1) 🎯 MVP

**Goal**: 筛选栏"语言"控件；选定即收窄列表（总数/分页一致）；与既有条件交集组合；一步清除恢复；查询复位页码；空态明确

**Independent Test**: 多语言数据下选择"俄语（ru）"查询 → 仅 ru、总数分页正确；叠加其他条件核对交集；清除恢复；空语言呈空态、页码越界不空白（quickstart L1+L4）

### Tests for User Story 1 ⚠️（先写，确认失败）

- [X] T182 [P] [US1] 后端契约测试（**行为锁定，书写即绿**）：`backend/tests/contract/test_seeds_api.py` 新增 `TestSeedLangFilter`——`GET /seeds?lang=ru` 仅返回 ru（另建 en 对照）；精确匹配（`EN` 与 `en` 互不混淆）；与 `status`/`review_status`/`q` 组合为交集且 `total` 一致；无匹配 → `200` + `total:0`、`items:[]`；**无副作用**（筛选前后数据不变，FR-009）（contracts §1；FR-002/003）——5 项书写即绿（契约锁定）
- [X] T183 [P] [US1] 组件测试（红）：`frontend/tests/seed-lang-filter.test.ts`——mock `src/api/client` 按路径分发（`/graph/nodes`、`/seeds/langs`、`/seeds`、`/llm/providers`），挂载复用 002 `theme-switch.test.ts` 模式（Pinia + memory Router + ElementPlus + i18n）：① 渲染"语言"筛选控件（`data-test="lang-filter"`）且默认未选择；② 选项 = 标准 17 语言 + `/seeds/langs` 返回的非标准值（标准语言即使库内无种子也在列）；③ 经 v-model 选 `ru` + 点"查询" → `/seeds` 请求参数含 `lang:'ru'` 且 `page:1`；④ 清除 + 查询 → 请求不含 `lang`；⑤ 翻到第 2 页后再查询 → `page:1`（FR-008）；⑥ 结果为空 → 表格空态文案"没有符合当前筛选条件的种子"（FR-007）——5 项确认失败（控件/空态缺失）

### Implementation for User Story 1

- [X] T184 [US1] 筛选控件实现：`frontend/src/views/seeds/SeedList.vue`——筛选栏新增语言 `el-select`（clearable、`data-test="lang-filter"`、与其他筛选项同排）；`filters.lang` 默认 `''`（空值不经 `buildQuery` 发起参数）；`load()` 内并行拉取 `/seeds/langs` 并经 `langFilterOptions` 组装选项（随每次刷新同步，FR-006）；新增 `onQuery()`（查询按钮与搜索词回车触发）→ `page=1` 后加载；表格 `empty-text="没有符合当前筛选条件的种子"`；既有 market_id 路由带入与其余筛选保持不变 → T183 转绿（FR-001~008；vitest 29 通过 + lint clean）
- [X] T185 [US1] 交互验收（quickstart L1+L4）：真实运行（构建产物 + `--server` + headless Chrome/CDP）——多语言数据下 ru 筛选（60 条零混杂）、组合交集（搜索词/审核）、清除恢复（一步 69 条）；空语言空态（fa→明确文案）；第 2 页改选不足一页语言 → 复位第 1 页有效结果；9 项全过、控制台 0 错误，结论已勾注 `specs/003-seed-language-filter/quickstart.md`

**Checkpoint**: US1 可独立演示——语言筛选可用（MVP）

---

## Phase 4: User Story 2 - 语言筛选融入既有运营工作流 (Priority: P2)

**Goal**: 翻译复核（语言+待审核）与执行准备（语言+状态+审核）可用；结果内操作保持语言条件；选项始终与库内同步

**Independent Test**: 翻译/模拟产出 ru 待审核种子 → "语言=ru+审核=待审核"筛出全部产出并采纳；"语言=ru+执行状态=待执行+审核=已采纳"得到执行清单（quickstart L2）

### Tests for User Story 2 ⚠️

- [X] T186 [US2] 组件测试（**书写即绿——US1 的 `load()` 即满足**）：`frontend/tests/seed-lang-filter.test.ts` 增补——① 选项随列表刷新同步：查询后再次调用 `/seeds/langs`，新返回的语言值立即出现在选项中（FR-006 不变量）；② 在语言筛选结果内执行"失效"操作 → 刷新请求仍携带当前 `lang`（语言条件保持、不清零，FR-010）——2 项书写即绿（vitest 31 通过，零额外实现得到证实）

### Implementation for User Story 2

- [X] T187 [US2] 工作流验收（quickstart L2）：真实运行（CDP 驱动 + 真实审核流转）——模拟翻译产出 6 条待审核 ru；"语言=ru+审核=待审核"筛出恰好该批（SC-006 一致）；采纳后"语言=ru+执行状态=待执行+审核=已采纳"→66 条全量核对、执行清单子集零混杂；结果内"失效"后列表保持语言条件刷新（6→5）；8 项全过、0 控制台错误，结论已勾注 quickstart

**Checkpoint**: US1+US2 成立——语言筛选在多语言运营链路中可用

---

## Phase 5: User Story 3 - 筛选选项对库内语言全覆盖（可见即可筛） (Priority: P3)

**Goal**: 导入/回灌带入的非标准代码与大小写变体均可选、可筛，无死角

**Independent Test**: 导入含 `ko`、`EN` 的种子 → 选项原样可见 → 分别筛选互不混淆（quickstart L3）

### Tests for User Story 3 ⚠️

- [X] T188 [P] [US3] 契约测试增补（**书写即绿——T179 按原值返回即满足**）：`backend/tests/contract/test_seeds_api.py`——`/seeds/langs`：非标准代码（`ko`）原样返回；大小写变体 `EN` 与 `en` 并存（不折叠、不归并）；新写入（`POST /seeds`）的取值即时出现在返回值（覆盖性）——2 项书写即绿（契约 23 全过）
- [X] T189 [P] [US3] 组件测试增补（**书写即绿——T181/T184 即满足**）：`frontend/tests/seed-lang-filter.test.ts`——mock `/seeds/langs` 返回 `['EN','en','ko','ru']`：选项中 `EN`、`ko` 原样渲染（不与标准标签混淆）；选择 `EN` → 请求 `lang:'EN'`（精确）；`EN` 与 `en` 为两个独立选项、各自可筛——1 项书写即绿（vitest 32 通过 + lint clean）

### Implementation for User Story 3

- [X] T190 [US3] 全覆盖验收（quickstart L3）：真实运行（CDP 驱动）——导入 2 条 `ko` + 3 条 `EN` → 选项 19 项含原样变体 → `ko`/`EN`/`en` 分别筛出 2/3/4 条互不混淆（SC-003 死角 0）；7 项全过、0 控制台错误，结论已勾注 quickstart

**Checkpoint**: 三故事全部独立可用——语言筛选特性完整交付

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 契约/文档同步、性能与回归验收、一致性审查

- [X] T191 [P] 契约与文档同步：`specs/001-sales-tool/contracts/local-api.md` 种子知识库表增补 `GET /seeds/langs` 行、`GET/POST /seeds` 行说明补记 lang 筛选（003）；`specs/001-sales-tool/quickstart.md` S4 步骤补"在种子列表按语言筛选（003 增量）"（宪法"契约变更必须同步"）
- [ ] T192 [P] 性能与回归验收（quickstart L5）：脚本生成 10,000 条种子数据集 → 应用/清除语言筛选记录呈现时间 ≤ 1s（SC-005）且与既有同类筛选无可见退化；走查既有能力（排序、翻页、勾选、翻译、编辑、失效）回归缺陷 0（SC-007）；结论勾注 quickstart
- [ ] T193 回归与一致性：全量测试绿（`cd backend && uv run pytest` / `cd frontend && pnpm test && pnpm lint && pnpm build`）；`/speckit-analyze` 一致性审查（spec/plan/tasks/契约，0 CRITICAL、覆盖 100%）；处置项记入 spec/契约注记

**说明（冻结包冒烟）**：沿用 001 S1/S6/S10（种子列表在其覆盖内）；本特性零新依赖、无打包面变化，不新增冻结包冒烟场景（理由记入 T193 提交信息）。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖，可立即开始（T177 基线先于任何改动）
- **Foundational (Phase 2)**: 依赖 Setup——**阻塞**全部用户故事
- **User Stories (Phase 3+)**: 依赖 Foundational
  - US1（P1）→ US2（P2）→ US3（P3）按优先级顺序推进；US2/US3 的验收（T187/T190）依赖 US1 的控件可用
- **Polish (Phase 6)**: 依赖全部故事完成（T191 可与 US3 尾巴并行准备）

### User Story Dependencies

- **US1**: 依赖 Foundational（端点 + 纯函数）；不依赖 US2/US3
- **US2**: 依赖 US1（在同一控件上验证组合与操作链路）；**零额外实现**——`load()` 统一携带筛选条件并刷新选项即构造性满足（T186 若红则为 US1 实现缺陷）
- **US3**: 依赖 Foundational + US1；**零额外实现**——T179 按原值返回、T181/T184 按原值渲染即构造性满足（T188/T189 若红则为实现缺陷）

### Within Each User Story

- 测试任务先写并确认**失败**（标注"书写即绿"者为行为锁定/证实性测试，失败则按提示修复上游实现）
- 故事完成并通过 Checkpoint 验收后再进入下一优先级
- 每完成一个任务立即提交一次（任务与其测试同提交；提交信息含任务 ID 并说明"为什么"——宪法工作流质量门）

### Parallel Opportunities

- 同阶段 [P] 任务并行：T178/T180（后端契约测试与前端纯函数测试）；T182/T183（后端锁定测试与前端组件测试）；T188/T189（两测各不同文件）；T191/T192（文档与性能验收）
- 单人开发时按 T 序号顺序执行即可，[P] 仅标示无冲突关系

---

## Parallel Example: Phase 2 Foundational

```bash
# 同消息并行发起（不同文件、无相互依赖）：
Task: "契约测试 /seeds/langs（红）in backend/tests/contract/test_seeds_api.py"   # T178
Task: "纯函数单测 langFilterOptions（红）in frontend/tests/seed-lang-options.test.ts"  # T180
# 两者分别转绿：
Task: "实现 distinct_langs + GET /seeds/langs in backend/src/saler/core/seeds/service.py + backend/src/saler/api/routes/seeds.py"  # T179
Task: "实现 langFilterOptions in frontend/src/constants.ts"                      # T181
```

---

## Implementation Strategy

### MVP First（US1）

1. 完成 Phase 1: Setup（T177）
2. 完成 Phase 2: Foundational（T178–T181，关键——阻塞一切）
3. 完成 Phase 3: US1（T182–T185）
4. **停下验证**：quickstart L1+L4 独立验收（筛选/组合/清除/空态/页码）
5. 可演示可继续

### Incremental Delivery

1. Setup + Foundational → 选项基座就绪
2. US1 → 验证 → **MVP**（按语言收窄列表）
3. US2 → 验证（翻译复核与执行准备链路——"用起来"形态）
4. US3 → 验证（非标准代码全覆盖——"放心用"形态）
5. Polish → 契约同步 + 性能/回归验收 + 一致性审查（T193）

### Parallel Team Strategy

本特性单人开发即可线性推进；如需并行：A 线后端（T178/T179 → T182 → T188）、B 线前端（T180/T181 → T183/T184 → T186/T189），前端线段依赖后端端点契约（T179）先行完成；验收任务（T185/T187/T190/T192）合流执行。

---

## Notes

- `[P]` = 不同文件、无未完成依赖，可并行；`[USx]` 标签用于追溯（Setup/Foundational/Polish 不带标签）
- 测试一律先失败再实现（宪法第 I 条）；行为锁定/证实性测试（T182/T186/T188/T189）已注明"书写即绿"及其构造来源
- 每个任务完成即提交（提交信息含任务 ID；如 `T179: GET /seeds/langs——选项全覆盖的库内取值源（为什么：非标准代码可见即可筛）`）
- 任务编号自 T177 起延续 002（T176 止），避免提交信息 ID 冲突
- 契约变更台账：contracts/seed-lang-filter-contract.md §4 要求同步 001 local-api.md 与 quickstart（T191）
- 已知语义（研发须知）：精确匹配——`EN` 与 `en` 为两个独立选项，不做大小写折叠；查询动作统一复位页码为第 1 页，顺带修正既有"跨页改条件可能空白"边缘行为（提交信息中说明）
- 避免：模糊任务、同文件冲突（`frontend/tests/seed-lang-filter.test.ts` 由 US1→US2→US3 顺序触碰；`frontend/src/views/seeds/SeedList.vue` 仅 US1 触碰，US2/US3 零额外实现）、破坏故事独立性的跨故事依赖
