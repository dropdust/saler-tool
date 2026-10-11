---
description: "Task list for 应用前端主题（浅色 / 深色）"
---

# Tasks: 应用前端主题（浅色 / 深色）

**Input**: Design documents from `/specs/002-frontend-theme/`

**Prerequisites**: [plan.md](plan.md)（required）, [spec.md](spec.md)（required）, [research.md](research.md), [data-model.md](data-model.md), [contracts/theme-contract.md](contracts/theme-contract.md), [quickstart.md](quickstart.md), `.specify/memory/constitution.md`

**Tests**: 必含——项目宪法第 I 条（测试驱动开发，不可协商）要求先写可失败的测试再实现；本特性测试全部离线可跑（vitest + pytest，无需真实 WebView/外部服务）。

**Organization**: 任务按用户故事分组，每个故事可独立实现、独立测试、独立交付。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无未完成依赖）
- **[Story]**: 所属用户故事（US1–US3）
- 每个任务都包含确切文件路径
- 任务编号自 **T151** 起（延续 001 的 T150，避免提交信息任务 ID 冲突）

## Path Conventions

- 后端：`backend/src/saler/`、后端测试：`backend/tests/`
- 前端：`frontend/src/`、前端测试：`frontend/tests/`
- 本特性无打包脚本改动（沿用 001 的 `packaging/` 与冻结包冒烟流程）

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 基线核对与暗色主题基座引入

- [X] T151 基线绿灯核对（现有套件 `backend/tests/`、`frontend/tests/`）：`cd backend && uv run pytest -q`（200 passed）、`cd frontend && pnpm test && pnpm build`（vitest 1 passed / build OK）全部通过，作为后续 TDD 红→绿对照基线（不产生文件变更；结论记入本任务提交信息）
- [ ] T152 [P] 前端接入 EP 暗色变量与主题基座：新建 `frontend/src/styles/theme.css`（`html,body` 基底 `--el-bg-color`/`--el-text-color-primary`、`color-scheme` 亮/暗双态、图表主题变量 `--chart-edge-solid`/`--chart-edge-dashed` 亮/暗双套、预览保真基底变量 `--preview-surface-bg/fg/border` 两主题同值）；`frontend/src/main.ts` 增加 `element-plus/theme-chalk/dark/css-vars.css` 与 `styles/theme.css` 引入（零新增依赖，见 plan.md Technical Context）

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 偏好 KV（后端）与主题 store（前端）——US1/US2/US3 共同地基

**⚠️ CRITICAL**: 本阶段完成前，任何用户故事不得开始

- [X] T153 [P] 契约测试（红）：`backend/tests/contract/test_settings_api.py`——`ui_theme` 无行时 GET 返回默认 `"light"`；PUT 写入往返；非法值（`"blue"`/`123`/`null`）→ 400 `{code:"bad_request", message:"ui_theme 仅支持 light/dark"}` 且不写库；存储侧非法值读取归一为 `"light"`（contracts/theme-contract.md §1）
- [X] T154 实现：`backend/src/saler/services/settings_service.py`（`DEFAULTS` + `"ui_theme": "light"`；值域校验钩子 `validate_value`）+ `backend/src/saler/api/routes/settings.py`（PUT 接线校验、GET 读取归一）→ T153 转绿
- [X] T155 [P] 单元测试（红）：`frontend/tests/theme-store.test.ts`——`toggle()` 同帧翻转 `document.documentElement` 的 `dark` 类并以 `{values:{ui_theme}}` 调用 `PUT /settings`；PUT 失败保留会话内主题并提示、不回滚；`normalizeTheme` 非 `"dark"` 一律归 `"light"`；`current` 初值从 DOM 读取（data-model.md 状态机）
- [X] T156 实现：`frontend/src/stores/theme.ts`（`current`/`toggle()`/`normalizeTheme`；唯一 DOM 类操作者，视图禁止直接操作）→ T155 转绿

**Checkpoint**: 地基就绪——KV 键与主题 store 可用；用户故事可开始

---

## Phase 3: User Story 1 - 主题切换与全局即时生效 (Priority: P1) 🎯 MVP

**Goal**: 页头全局切换控件；两模式切换同帧全局生效、无需重启/刷新；不中断操作（未保存输入保留）；当前模式可辨识

**Independent Test**: 壳形态打开应用，从页头切 light→dark：全界面（含已开弹窗）即时切换、未保存表单保留；切回一致（quickstart T1）

### Tests for User Story 1 ⚠️（先写，确认失败）

- [X] T157 [P] [US1] 组件测试（红）：`frontend/tests/theme-switch.test.ts`——MainLayout 页头渲染主题切换控件（含中文 aria-label）；交互调用 `themeStore.toggle()`；控件当前态指示（图标/选中态）随 `theme.current` 变化

### Implementation for User Story 1

- [ ] T158 [US1] 页头切换控件：`frontend/src/layouts/MainLayout.vue`——页头（健康标签旁）新增 `el-switch` 内联 ☀️/🌙 图标主题切换，绑定 `stores/theme.ts`；切换同帧生效、不刷新页面、不触碰表单状态（FR-001~004）
- [X] T159 [US1] 交互验收（quickstart T1）：headless Chrome（CDP）自动驱动构建产物——class 同帧翻转、三处计算样式切换、未保存输入保留、PUT 往返持久化、0 控制台错误；结论已勾注 `specs/002-frontend-theme/quickstart.md`

**Checkpoint**: US1 可独立演示——主题切换即时全局生效（会话内）

---

## Phase 4: User Story 2 - 主题偏好记忆与启动呈现 (Priority: P2)

**Goal**: 选择被记住并随备份/迁移保留；重启首屏即目标主题、无可感知闪变；首启/损坏/缺失回退 light 且不阻断启动

**Independent Test**: dark → 退出 → 重启：首屏直接 dark 且录屏无闪变；非法值/删除行后重启回退 light；备份恢复/目录迁移后保持（quickstart T2+T5）

### Tests for User Story 2 ⚠️（先写，确认失败）

- [X] T160 [P] [US2] 注入路由单测（红）：`backend/tests/unit/test_theme_injection.py`——dist fixture 下：KV=dark → `GET /` 返回 HTML 注入 `class="dark"`（与既有 class 合并且不重复）；KV=light/无行 → 原样返回；存储非法值 → 按 light 原样；响应头 `Cache-Control: no-store`；`/assets/*` 静态资源不受影响；无 dist 时 `/` 仍 404（保持既有 `test_spa_mount.py` 语义）
- [X] T161 [P] [US2] 启动同步单测（红）：`frontend/tests/theme-boot.test.ts`——`syncFromServer()`：服务器 dark + DOM 无类 → 加类；`userTouched=true` → 不覆盖用户刚做的切换；`GET /settings` 失败 → 静默保持现状（dev 兜底/异常校正，R4）
- [X] T162 [P] [US2] 集成测试（红→绿）：`backend/tests/integration/test_us3_backup_restore.py`（书写即绿：ui_theme 随整库快照往返，零额外实现得到证实） 增补——设 `ui_theme=dark` → 生成备份 → 恢复 → `GET /settings` 得 `dark`（FR-012 随备份链保留的证据，预期零额外实现）

### Implementation for User Story 2

- [X] T163 [US2] 注入路由实现：`backend/src/saler/api/main.py`——`frontend_dist` 存在时、StaticFiles 挂载**之前**注册显式 `GET /`：同步读 `ui_theme` → 归一 → 注入 `<html …>` class（dark 时合并 `class="dark"`，light 原样）；读取异常回退 light + warning；`no-store`（contracts/theme-contract.md §2）→ T160 转绿
- [X] T164 [US2] 启动同步实现：`frontend/src/stores/theme.ts` 增 `syncFromServer()`（`userTouched` 守卫）+ `frontend/src/main.ts` 挂接启动调用 → T161 转绿
- [X] T165 [US2] 启动与迁移验收（quickstart T2+T5）：重启首屏字节级即 dark（早期采样 600ms 复核）→ 非法值/删行回退 light → 备份往返（T162）与真实数据目录迁移后主题保持；结论已勾注 `specs/002-frontend-theme/quickstart.md`

**Checkpoint**: US1+US2 成立——偏好持久、启动零闪变（本特性的"可日常使用"形态）

---

## Phase 5: User Story 3 - 双主题下的完整适配与内容保真 (Priority: P3)

**Goal**: 全部界面（含图谱/表格/弹窗/空态）两主题下完整可读、对比度达标；营销内容预览与素材保持"收件人视角"，不被主题反色

**Independent Test**: 以 quickstart 固定清单逐页走查两主题（缺陷 0）；抽查 ≥5 个模板确认预览/测试发送与主题无关；图谱 dark 下节点/边线/标签可读（quickstart T3+T4）

### Tests for User Story 3 ⚠️（先写，确认失败）

- [ ] T166 [P] [US3] palette 单测（红）：`frontend/tests/theme-palette.test.ts`——`readThemePalette()` 读取 mock computed 的 `--el-color-success/warning/primary/info`、`--el-text-color-primary`、`--el-bg-color-overlay`、`--el-border-color`、`--chart-edge-*`；变量缺失时兜底色；节点状态色语义映射不变（contacts>0→success、done>0→warning、seeds>0→primary、其余→info，R5）
- [ ] T167 [P] [US3] GraphView 主题化单测（红）：`frontend/tests/graphview-theme.test.ts`——mock `echarts`（不触真实 canvas）：主题值变化触发 setOption 重渲；节点/边线/label/tooltip 颜色取自 palette

### Implementation for User Story 3

- [ ] T168 [US3] palette 实现：`frontend/src/theme/palette.ts`（`readThemePalette()` 经 `getComputedStyle(document.documentElement)` 读 EP 变量；节点色映射纯函数）→ T166 转绿
- [ ] T169 [US3] GraphView 主题化落地：`frontend/src/views/seeds/GraphView.vue`——`colorOf` → palette；边线 `--chart-edge-solid/dashed`；label/tooltip 主题色；图例圆点硬编码色改 CSS 变量；`watch(themeStore.current)` 复用 `renderChart()` 重渲 → T167 转绿（FR-008）
- [ ] T170 [US3] 内容保真：`frontend/src/views/content/VariantEditor.vue`——预览区 `.preview-body`/`.preview-subject` 改用 `--preview-surface-*` 保真基底（两主题同值：白底深字固定边框），`html.dark` 下不反色（FR-010）
- [ ] T171 [US3] 硬编码颜色清零核查：`frontend/src/` 全仓 grep（颜色声明含 `#hex|white|black` 且不含 `var(--el`）——除保真基底豁免外应为 0，修复遗漏（FR-008；与 contracts/theme-contract.md §3"禁止硬编码颜色"一致）
- [ ] T172 [US3] 双主题全界面走查（quickstart T3+T4）：按固定清单逐页勾选（含 DevTools 对比度抽查 ≥4.5:1、图谱 dark 可读、预览保真、素材图片不反色）；缺陷即时修复（修复任务补记于本文件）；结论勾注 `specs/002-frontend-theme/quickstart.md`

**Checkpoint**: 三故事全部独立可用——主题特性完整交付

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 契约/文档同步、冻结包冒烟、回归与一致性

- [ ] T173 [P] 契约与文档同步：`specs/001-sales-tool/contracts/local-api.md` settings 行补记 `ui_theme` 键与值域；`specs/001-sales-tool/quickstart.md` S1 增补"首启默认 light + 页头切换可达"断言（宪法"契约变更必须同步"）
- [ ] T174 [P] 冻结包冒烟增量（quickstart T6）：本机 Linux 以构建产物执行 ①–⑤（首启 light / 切换即时 / 重启保持且无闪变录屏 / 图谱 dark 可读 / 备份恢复保留）；Windows/macOS 项并入 001 S12 发布流程执行
- [ ] T175 回归与一致性：全量测试绿（`backend` pytest + `frontend` vitest + `pnpm build`/`vue-tsc`）；运行 `/speckit-analyze` 对 002 工件做一致性审查并处置发现项

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖，可立即开始（T151 基线先于任何改动）
- **Foundational (Phase 2)**: 依赖 Setup——**阻塞**全部用户故事
- **User Stories (Phase 3+)**: 依赖 Foundational
  - US1（P1）→ US2（P2）→ US3（P3）按优先级顺序推进；US3 的走查验收（T172）需 US1+US2 完成
- **Polish (Phase 6)**: 依赖全部故事完成（T173 可与 US 阶段尾巴并行准备）

### User Story Dependencies

- **US1**: 仅依赖 Foundational（会话内切换即可独立演示；持久化由 US2 补全）
- **US2**: 依赖 Foundational；与 US1 的集成点在 `stores/theme.ts`（US2 增 `syncFromServer`，不改 `toggle`）
- **US3**: 实现（T168/T169/T170/T171）与 US1/US2 无代码依赖；验收（T172）依赖前两者可用以完成走查

### Within Each User Story

- 测试任务先写并确认**失败**，再实现转绿（宪法第 I 条）
- 故事完成并通过 Checkpoint 验收后再进入下一优先级
- 每完成一个任务立即提交一次（任务与其测试同提交；提交信息含任务 ID 并说明"为什么"——宪法工作流质量门）

### Parallel Opportunities

- 同阶段 [P] 任务并行：T153/T155（后端契约测试与前端 store 测试）；T160/T161/T162（三份测试互不同文件）；T166/T167（palette 与 GraphView 测试）；T173/T174（文档与冒烟）
- 单人开发时按 T 序号顺序执行即可，[P] 仅标示无冲突关系

---

## Parallel Example: Phase 2 Foundational

```bash
# 同消息并行发起（不同文件、无相互依赖）：
Task: "契约测试 ui_theme（红）in backend/tests/contract/test_settings_api.py"        # T153
Task: "单元测试 主题 store（红）in frontend/tests/theme-store.test.ts"               # T155
# 两者分别转绿：
Task: "实现 settings_service ui_theme 键与校验 in backend/src/saler/services/settings_service.py"  # T154
Task: "实现主题 store in frontend/src/stores/theme.ts"                              # T156
```

---

## Implementation Strategy

### MVP First（US1）

1. 完成 Phase 1: Setup（T151–T152）
2. 完成 Phase 2: Foundational（T153–T156，关键——阻塞一切）
3. 完成 Phase 3: US1（T157–T159）
4. **停下验证**：quickstart T1 独立验收（切换即时生效、操作不中断）
5. 可演示可继续

### Incremental Delivery

1. Setup + Foundational → 地基就绪
2. US1 → 验证 → **MVP**（切换即时全局生效）
3. US2 → 验证（记忆、零闪变启动、备份迁移保留——"可日常使用"形态）
4. US3 → 验证（全界面适配、对比度、内容保真——"放心用"形态）
5. Polish → 契约同步 + 冻结包冒烟 + 一致性审查（T175）

### Parallel Team Strategy

多人协作时：Setup+Foundational 共同完成；此后 A 线 US1→US2（前端切换与启动链路）、B 线 US3 的 palette/GraphView/保真实现（T166/T168/T169/T170 与前端 A 线不冲突），最后合流 US3 走查（T172）与 Polish。

---

## Notes

- `[P]` = 不同文件、无未完成依赖，可并行；`[USx]` 标签用于追溯（Setup/Foundational/Polish 不带标签）
- 测试一律先失败再实现（宪法第 I 条）；本特性无需外部服务，全部离线可测
- 每个任务完成即提交（提交信息含任务 ID；如 `T154: 设置 KV 增 ui_theme——主题偏好持久化底座（为什么：备份链零成本保留）`）
- 任务编号自 T151 起延续 001（T150 止），避免提交信息 ID 冲突
- 契约变更台账：contracts/theme-contract.md §1 同步 001 local-api.md（T173）；HTML 注入行为属新增服务约定（§2）
- 已知限制（研发须知）：Vite dev 无注入 → 启动可能瞬时 light→dark；首屏零闪变以壳形态验收（quickstart §1）
- 避免：模糊任务、同文件冲突（`stores/theme.ts` 由 Foundational 与 US2 顺序触碰，不并行）、破坏故事独立性的跨故事依赖
