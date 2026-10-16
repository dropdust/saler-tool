---
description: "Task list for AI 提示词自定义与辅助编写（扩充 / 起草）"
---

# Tasks: AI 提示词自定义与辅助编写（扩充 / 起草）

**Input**: Design documents from `/specs/006-ai-prompt-customization/`

**Prerequisites**: [plan.md](plan.md)（required）, [spec.md](spec.md)（required）, [research.md](research.md), [data-model.md](data-model.md), [contracts/prompt-customization-contract.md](contracts/prompt-customization-contract.md), [quickstart.md](quickstart.md), `.specify/memory/constitution.md`

**Tests**: 必含——项目宪法第 I 条（测试驱动开发，不可协商）要求先写可失败的测试再实现；本特性测试全部离线可跑（pytest + vitest；LLM 一律 FakeLLMProvider / mock api 客户端，零真实外网依赖）。标注"红→绿"的任务严格先失败后实现；纯接线类（类型/薄封装）注明"书写即绿"。

**Organization**: 任务按用户故事分组（US1 自定义扩充提示词 / US2 自定义起草提示词 / US3 AI 辅助编写），每个故事可独立实现、独立测试、独立交付；US2/US3 复用 US1 建立的编辑器组件与端点（不同 feature 参数/不同 UI 挂载点），US3 的辅助能力挂在 US1 的编辑器上增量交付。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无未完成依赖）
- **[Story]**: 所属用户故事（US1–US3）；Setup/Foundational/Polish 不带标签
- 每个任务都包含确切文件路径
- 任务编号自 **T278** 起（延续 005 的 T277 收尾，避免提交信息任务 ID 冲突）

## Path Conventions

- 后端：`backend/src/saler/`、后端测试：`backend/tests/`
- 前端：`frontend/src/`、前端测试：`frontend/tests/`
- 本特性**零新增依赖、无数据库迁移、无打包面变化**（复用 `app_setting` KV 与 `llm_call` 表；沿用 001/005 冻结包冒烟与验收配方）

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 基线核对，建立在途改动隔离基线

- [X] T278 基线核对与工件入库：在途他线改动（005 US2 收尾：`frontend/src/views/seeds/AiExpandDialog.vue`、`frontend/src/views/content/AiContentDialog.vue`、`frontend/src/views/seeds/SeedList.vue`、`frontend/src/api/jobs.ts`、`frontend/src/components/common/JobRunPanel.vue`、`frontend/tests/dialog-background.test.ts`、`frontend/tests/ai-expand-calls-entry.test.ts` 等）按 005 T226 隔离策略处理——**尽量先与其归位（完成对应 005 任务提交）再开始本特性**：T286/T289 将顺序触碰两个对话框文件，避免同文件交叉改动；基线 `cd backend && uv run pytest -q` 全绿、`cd frontend && pnpm test` 全绿 + `pnpm lint` clean；同期搭载 006 规格工件入库（spec/plan/research/data-model/contracts/quickstart/tasks/checklists）→ 回填核对结论（2026-10-16 实作：005 在途改动归位为独立提交 8cfc729「T238~T241 对话框转后台实作收口」；基线 backend 398 passed / frontend 192 passed（24 文件）+ lint clean——基线绿，进入 Phase 2）

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 全部用户故事共同依赖的基座——提示词注册表（两功能定义/渲染/组合/校验）、设置存取（含删行）、前端类型与薄封装

**⚠️ CRITICAL**: 本阶段完成前，任何用户故事不得开始

- [X] T279 [P] 后端：提示词注册表（红→绿）：新建 `backend/src/saler/core/prompts/__init__.py` 与 `backend/src/saler/core/prompts/registry.py`（纯函数模块，**不得依赖 FastAPI/DB**）——
  ① 两功能定义（data-model.md §2.1 逐字照录）`seed_expand` / `content_draft`：展示名、默认模板全文（由现文案机械重构：`core/seeds/ai.py:build_expansion_prompt` / `core/content/ai.py:_build_draft_prompt` 的固定部分抽出为固定段，其余按原顺序入模板、动态数据处换变量 token、固定段位置留 `{output_contract}` 槽位）、固定段原文、变量目录（name/label/render 说明，data-model.md §2.2 语义表逐条落实，含边界：`{description}` 空→`""`、`{existing_nodes}` 空→`""` 且按 产品线/客户角色/市场(国家) 顺序、`{tone}` 缺省→「语气：专业、克制、以价值为先。」）、长度上限 **8000**；
  ② `compose(feature, template, context) -> str`：已知变量精确 token 替换（`str.replace`，未知 token 原样透传）、`{output_contract}` → 固定段原文、**模板缺失槽位时自动补于末尾**（`\n\n` 分隔）；
  ③ `validate_template(feature, content) -> (errors, warnings)`：空/纯空白与超长 → errors（消息含额度与当前长度）；未知变量（去重逐一、`{{...}}` 豁免：扫描正则负向断言见 research R2）、任一已知数据变量未引用（逐一）、槽位缺失 → warnings（contract §7 码表 `unknown_variable`/`missing_variable`/`missing_output_contract`）；
  ④ 渲染用标签映射自带（产品线/客户角色/市场/国家），与 `core/seeds/ai.py:NODE_TYPE_LABELS` 不互相 import（防循环依赖）；
  新建 `backend/tests/unit/test_prompt_registry.py`——**golden 等价**：文件内以手抄现文案的 `_legacy_seed_prompt`/`_legacy_draft_prompt` 基准函数（复制自现实现，冻结历史）对代表性上下文（常规/空描述/空节点/缺省语气/边界数量）断言 `compose(默认模板) == legacy 输出` **逐字相等**（SC-002 回归口径）；渲染语义逐条、槽位替换与缺失兜底、`{{company_name}}`/`{{signature}}` 不被扫描替换、校验三警告与两错误码（contract §6/§7）→ **红→绿**（2026-10-16 实作：24 项红→绿——含 9 例 golden 逐字等价与空白语气/空白描述边界；全量 422 passed）

- [X] T280 [P] 后端：设置基座（红→绿）：`backend/src/saler/services/settings_service.py` 增 `delete_value(db, key)`（删行并 commit；对不存在键幂等）；`backend/src/saler/api/routes/settings.py` 的 `put_settings` 增守卫——`key.startswith("prompt_template_")` 一律 400 `bad_request`（消息指引走 AI 提示词接口；**置于 `is_known_key` 检查之前**，防行存在后被通用端点写脏形状）；扩展 `backend/tests/contract/test_settings_api.py`（delete 幂等单测 + 通用 PUT 拒绝两类提示词键：无行时、有行时）→ **红→绿**（2026-10-16 实作：3 项红→绿，全量 425 passed）

- [X] T281 后端：模板存取服务（红→绿，依赖 T279/T280）：新建 `backend/src/saler/core/prompts/store.py`——`get_effective(db, feature) -> (content, customized)`（经 `settings_service.get(db, "prompt_template_{feature}", None)`；无行 → 注册表默认 + `customized=False`）、`save(db, feature, content)`（校验通过后写 `{"content": …}`）、`reset(db, feature)`（`delete_value`）；键名常量与功能列表从 registry 派生；新建 `backend/tests/unit/test_prompt_store.py`（无行回默认、保存后 customized=True、reset 回默认且幂等、两功能键互不影响）（data-model.md §1）→ **红→绿**（2026-10-16 实作：7 项绿——另增脏数据行缺 content 回落默认的防御用例；全量 432 passed）

- [X] T282 [P] 前端：契约小件（书写即绿）：`frontend/src/api/types.ts` 增 `PromptVariable`（name/label/render）、`PromptTemplateSummary`（feature/label/customized/updated_at）、`PromptTemplateDetail`（content/default_content/customized/updated_at/max_length/variables/reserved_variables/output_contract）、`PromptWarning`（code/message）、`PromptAssistResponse`（suggestion/notes）类型；新建 `frontend/src/api/prompts.ts` 薄封装（`getPromptList()` / `getPrompt(feature)` / `savePrompt(feature, content)` / `resetPrompt(feature)` / `assistPrompt(feature, payload)`，泛型返回上述类型）；以类型编译与后续组件测试间接覆盖（contract §1~§5 形状）（2026-10-16 实作：vue-tsc 通过、lint clean）

**Checkpoint**: 基座就绪——注册表/存取/类型齐备，用户故事可开始

---

## Phase 3: User Story 1 - 自定义「AI 扩充」的提示词 (Priority: P1) 🎯 MVP

**Goal**: 扩充对话框内可打开提示词编辑器（默认模板/变量面板/固定段只读块/状态徽标），修改保存后新发起的扩充使用自定义模板且调用明细完整可见；一键恢复默认；未自定义用户行为与升级前逐字一致

**Independent Test**: 打开扩充对话框 → 编辑器核对默认全文/变量/槽位/额度 → 加入可辨认指令保存（≤3 操作）→ 发起扩充 → 调用明细核对自定义文本 + 变量已替换 + 固定段在位 → 产出体现指令且照常入待审核 → 恢复默认核对还原；不自定义用户走 quickstart V4 默认等价（quickstart V1 + V4）

### Tests for User Story 1 ⚠️（先写，确认失败）

- [X] T283 [US1] 模板端点契约（红→绿，依赖 T281）：`backend/src/saler/api/routes/ai.py` 增四端点——`GET /ai/prompts`（两功能 `{feature,label,customized,updated_at}` 固定顺序）、`GET /ai/prompts/{feature}`（详情形状 contract §2：content/default_content/customized/updated_at/max_length=8000/variables/reserved_variables/output_contract；未知 feature → 404 `not_found`）、`PUT /ai/prompts/{feature}`（保存：空/超长 → 400 `bad_request` 且消息含额度；成功 200 = 详情 + `warnings[]` 且 customized 置 true）、`POST /ai/prompts/{feature}/reset`（200 详情 customized=false、幂等）；新建 `backend/tests/contract/test_ai_prompts_api.py`——§1~§4 全形状、404、400 双例、warnings 三码（含 `{{...}}` 不误报）、恢复默认与两功能独立性（保存 seed_expand 不影响 content_draft）→ **红→绿**（2026-10-16 实作：13 项红→绿——含 2 例"FastAPI 默认 404 恰好通过"的占位用例在实现后仍绿；另补 store.get_row 供 API 呈现 updated_at（宪法 II：路由不直接碰模型）；全量 445 passed）

- [X] T284 [US1] 扩充运行接入组合管线（红→绿，依赖 T279/T281）：`backend/src/saler/core/seeds/ai.py`——`run_expansion` 删除 `build_expansion_prompt` 硬编码路径（函数一并删除，`test_seed_ai.py` 若有引用同步迁移），改为任务开始执行时 `store.get_effective(db, "seed_expand")` 取一次、`registry.compose` 组合入 `provider.generate_structured`；`NODE_TYPE_LABELS` 保留供节点类型校验，新增与 registry 渲染标签的一致性断言（防漂移）；扩展 `backend/tests/unit/test_seed_ai.py`——先经 `store.save` 写入自定义模板（含可辨认文本）再运行，断言 FakeLLMProvider 收到的 messages[user] 含自定义文本、`{description}`/`{existing_nodes}`/`{count}` 已替换、固定段在位、系统消息仍为 JSON 守门；默认路径另以 golden 互验（T279）；脚本化无效输出核对失败呈现沿用既有路径（FR-013）→ **红→绿**（2026-10-16 实作：自定义模板用例红→绿；默认路径用例书写即绿——golden 等价生效；标签一致性断言已在 T279 落位 test_prompt_registry；全量 447 passed）

- [X] T285 [US1] 提示词编辑器组件（红→绿，依赖 T282）：新建 `frontend/src/components/common/PromptEditorDialog.vue`——打开经 `getPrompt(feature)` 载入（标题旁「默认/已自定义」徽标）；模板文本域（实时长度/剩余额度，上限 8000）；变量面板（可编辑变量 + `reserved_variables` 槽位，各含 name/label/render 说明，点击插入光标处 `{name}`）；固定段只读块（呈现"`{output_contract}` 处将替换为…"及其原文）；保存流（客户端同规则预检 → 有警告先 `ElMessageBox.confirm`「仍要保存/取消」→ `savePrompt` → 成功提示 + 响应 warnings 逐条 warning 提示；400 走统一错误包）；「恢复默认」（二次确认 → `resetPrompt` → 编辑器回显默认全文）；脏状态关闭确认放弃；`frontend/tests/prompt-editor-dialog.test.ts`（mock api 客户端）——载入渲染/徽标两态、长度计数、变量点击插入、保存预检警告确认与取消两路径、400 呈现、恢复默认回显、脏关闭确认（contract §8、quickstart V1 的 ②③⑥ 步）→ **红→绿**（2026-10-16 实作：10 项红→绿；el-input 透传属性落内部 textarea、模板内 `{` 开头模板串需改字符串拼接两个实现陷阱修正；全量 202 passed + lint + vue-tsc clean。辅助区留待 T292 增量）

### Implementation for User Story 1

- [ ] T286 [US1] 扩充对话框接入入口（红→绿，依赖 T285）：`frontend/src/views/seeds/AiExpandDialog.vue` 增「提示词」入口（表单态可见；旁挂「默认/已自定义」徽标，打开对话框时经 `getPromptList` 取数）+ 挂载 `PromptEditorDialog`（feature=`seed_expand`，append-to-body 叠层）；保存/恢复后徽标即时刷新；扩展 `frontend/tests/ai-expand-calls-entry.test.ts`——入口出现、徽标两态、点击以正确 feature 打开编辑器、编辑器保存回调刷新徽标（FR-002、contract §8）→ **红→绿**

- [ ] T287 [US1] 验收（quickstart V1 + V4）：按 [quickstart.md](quickstart.md) 执行——编辑器全要素核对、≤3 操作保存、扩充运行后明细逐项核对（自定义文本/变量替换/固定段/系统消息）、产出体现指令、恢复默认还原、边界抽查（空/超长/未知变量/缺变量/缺槽位兜底）、运行中修改不影响在途运行；不自定义路径执行 V4 默认等价；结论勾注（SC-001~004、FR-001~008）→ 回填验收结论

**Checkpoint**: US1 完成——扩充提示词可自定义、可核对、可回退，构成 MVP

---

## Phase 4: User Story 2 - 自定义「AI 起草」的提示词 (Priority: P2)

**Goal**: 起草对话框（起草/润色母版页签）同款编辑器接入；新发起的起草使用自定义模板；两功能模板互相独立

**Independent Test**: 起草页签打开编辑器核对默认/变量（业务要点/语气/内容类型/语言）→ 加入可辨认写作约束保存 → 发起起草核对明细（变量渲染语义两态：`{tone}` 有值/缺省）与 `{{company_name}}`/`{{signature}}` 未被误替换 → 产出入草稿待审核 → 扩充模板不受影响（quickstart V2）

### Tests for User Story 2 ⚠️（先写，确认失败）

- [ ] T288 [US2] 起草运行接入组合管线（红→绿，依赖 T279/T281）：`backend/src/saler/core/content/ai.py`——`run_content_draft` 删除 `_build_draft_prompt` 硬编码路径（函数一并删除），改为任务开始时 `store.get_effective(db, "content_draft")` + `registry.compose`（上下文：`brief`/`tone`（None→缺省渲染）/`content_type`（主题值）/`language`（母版语言））；新建 `backend/tests/unit/test_content_ai.py`——自定义模板生效断言（FakeLLMProvider messages 含自定义文本、`{brief}`→「业务要点：…」、`{tone}` 两态、`{{company_name}}` 原样保留、固定段在位）；默认路径 golden 互验；两功能独立（改扩充模板不影响起草运行）→ **红→绿**

- [ ] T289 [US2] 内容对话框接入入口（红→绿，依赖 T285）：`frontend/src/views/content/AiContentDialog.vue` 起草/润色页签增「提示词」入口 + 徽标（feature=`content_draft`，「主题级多语言生成」页签不加）+ 挂载编辑器；文档范围提示保持既有口径；扩展 `frontend/tests/dialog-background.test.ts`（或按现状归属该对话框的测试文件）——起草页签入口出现、语言生成页签无入口、以正确 feature 打开编辑器 → **红→绿**

### Implementation for User Story 2

- [ ] T290 [US2] 验收（quickstart V2）：按 quickstart 执行起草模板自定义端到端（含 `{tone}` 两态与占位符豁免核对、两功能独立核对）；结论勾注（FR-001~003/007、US2 场景）→ 回填验收结论

**Checkpoint**: US2 完成——两处 AI 使用点均可自定义，模板互相隔离

---

## Phase 5: User Story 3 - AI 辅助编写提示词 (Priority: P3)

**Goal**: 编辑器内以意图生成候选模板、对草稿润色/优化；建议态呈现（采用≠保存）；辅助调用同步执行并落 `llm_call` 明细（`operation=prompt_assist`、`job_id=NULL`）；未配置服务给出指引且编辑器功能无损

**Independent Test**: 编辑器输入意图「AI 生成」→ 建议含必要变量且不改固定段 → 采用仅入编辑器、不保存 → 丢弃原文不变；「AI 优化」对照呈现；调用明细可见辅助完整出入参；未配置 → 409 指引（quickstart V3）

### Tests for User Story 3 ⚠️（先写，确认失败）

- [ ] T291 [US3] 辅助后端（红→绿，依赖 T279/T281）：`backend/src/saler/providers/llm/schemas.py` 增 `PROMPT_ASSIST_V1_SCHEMA`（`{suggestion: string, notes: string|null}`，`required=[suggestion]`）；新建 `backend/src/saler/core/prompts/assist.py`——`build_assist_prompt(feature, mode, intent, draft)`（system=提示词工程助手纪律；user=功能名+变量目录（含渲染语义）+固定段原文（"不得重复或修改"）+模式参数+输出要求；research R8）；`run_prompt_assist(session_factory, provider, *, feature, mode, intent, draft) -> dict`（`generate_structured(PROMPT_ASSIST_V1_SCHEMA, timeout_s=60, deadline_s=60)`，`CallRecorder(job_id=None, operation="prompt_assist")` 逐次落行 + `telemetry.record_from_provider`）；`backend/src/saler/api/routes/ai.py` 增 `POST /ai/prompts/{feature}/assist`（同步 `def` 路由，线程池执行；`resolve_llm_provider(db, None)` 未配置 → 既有 409 `llm_not_configured`；`generate` 缺 `intent` / `polish` 缺 `draft` / 非法 mode → 400 `bad_request`；**不落业务库**）；扩展 `backend/tests/contract/test_ai_prompts_api.py`——generate/polish 成功（monkeypatch 假 provider 或 FakeLLMProvider 注入）响应形状、400 三例、409 门控、`llm_call` 落行断言（operation/job_id NULL/start+finish 收口/response 含 suggestion）、telemetry 记账（contract §5、FR-009~012）→ **红→绿**

- [ ] T292 [US3] 编辑器辅助 UI（红→绿，依赖 T285/T291）：`frontend/src/components/common/PromptEditorDialog.vue` 增辅助区——意图输入 +「AI 生成」（≤2000 字）；「AI 优化当前草稿」（取编辑器当前文本）；请求期 loading 且文本可继续编辑；建议区展示 `suggestion` 全文与 `notes`，「采用」（写入编辑器、dirty=true、**不自动保存**）与「丢弃」；辅助完成后「查看调用明细」入口（`LlmCallsDrawer.open({operation:'prompt_assist'})`）；409 呈现「设置 → 大模型」指引且编辑器内容无损；扩展 `frontend/tests/prompt-editor-dialog.test.ts`——两模式触发与请求参数、建议渲染、采用不保存（关闭后重开已保存模板不变）、丢弃原文不变、辅助失败/409 内容无损与指引、明细入口以 operation 打开（contract §8、FR-010~012）→ **红→绿**

### Implementation for User Story 3

- [ ] T293 [US3] 验收（quickstart V3）：按 quickstart 执行辅助全链（生成/采纳/丢弃/优化/明细/409 指引；常规网络响应 ≤30s 抽查）；结论勾注（SC-005/006、FR-009~012）→ 回填验收结论

**Checkpoint**: US3 完成——写不好提示词的用户也能获得可用模板

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 契约同步、全量回归与质量门、边界抽查与文档

- [ ] T294 契约同步（宪法"契约变更必须同步"）：按 [contracts/prompt-customization-contract.md](contracts/prompt-customization-contract.md) §9 增补 `specs/001-sales-tool/contracts/local-api.md` §AI 节——4 个新端点（GET /ai/prompts、GET/PUT /ai/prompts/{feature}、POST …/reset、POST …/assist）与 `llm_call.operation` 新取值 `prompt_assist`（既有行不改）；核对 006 工件间一致性（spec/plan/research/data-model/contract/quickstart）
- [ ] T295 全量回归与质量门：`cd backend && uv run pytest -q` 全量绿、`cd frontend && pnpm test && pnpm lint` 全量绿；运行 `/speckit-analyze` 核对工件间一致（0 CRITICAL）；重点回归既有 `backend/tests/unit/test_seed_ai.py` 与内容流集成测试（运行管线替换不破坏既有断言，如破坏则更新断言并说明"为什么"）
- [ ] T296 边界抽查与文档：quickstart V1 边界集复跑（空/超长/未知变量/缺变量/缺槽位兜底/运行中修改）；`docs/user-guide.md` 增「AI 提示词自定义与辅助」一节（入口/变量/固定结构/恢复默认/辅助与采用语义/明细核对的用户口径）；勾注 quickstart 全部场景结论

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup（T278）**：无依赖，立即开始；**前置纪律**：在途 005 改动尽量归位后再开（T286/T289 触碰同文件）
- **Foundational（T279–T282）**：依赖 Setup——**阻塞全部用户故事**；T279/T280/T282 相互独立可并行（三个不同文件域），T281 依赖 T279+T280
- **US1（T283–T287）**：T283/T284 可并行（端点 vs 运行管线，均依赖 T281）；T285 依赖 T282；T286 依赖 T285；T287 收尾
- **US2（T288–T290）**：T288 依赖 T281（与 US1 后端线并行）；T289 依赖 T285（US1 组件）；T290 收尾
- **US3（T291–T293）**：T291 依赖 T281（与 US1/US2 并行线）；T292 依赖 T285+T291；T293 收尾
- **Polish（T294–T296）**：依赖全部故事完成

### Within Each User Story

- 测试（红）先于实现（绿）；服务/端点先于 UI 挂载；每完成一个任务立即提交一次（任务与其测试同提交；提交信息含任务 ID 并说明"为什么"——宪法工作流质量门）

### Parallel Opportunities

- Foundational：T279/T280/T282 并行（registry / settings / 前端类型三域互不触碰）
- US1：T283/T284 并行（`api/routes/ai.py` vs `core/seeds/ai.py`）；T283 与 US2 的 T288 并行（`api/routes/ai.py` vs `core/content/ai.py`）
- US3：T291 与 US2 前端线（T289）并行（`core/prompts/assist.py`+`schemas.py` vs `AiContentDialog.vue`）

---

## Parallel Example: Foundational

```bash
# 同一消息并行发起（各自独立文件域）：
Task: "提示词注册表 in backend/src/saler/core/prompts/registry.py"       # T279
Task: "设置基座 in backend/src/saler/services/settings_service.py"       # T280
Task: "前端契约小件 in frontend/src/api/types.ts + prompts.ts"            # T282

# US1 后端双线（T281 完成后）：
Task: "模板端点契约 in backend/src/saler/api/routes/ai.py"                # T283
Task: "扩充运行接入 in backend/src/saler/core/seeds/ai.py"                # T284
```

---

## Implementation Strategy

### MVP First（US1）

1. Phase 1 Setup（T278，含在途归位纪律）
2. Phase 2 Foundational（T279–T282，关键——阻塞一切）
3. Phase 3 US1（T283–T287）
4. **停下验证**：quickstart V1 + V4 独立验收（自定义生效 + 默认逐字等价）
5. 可演示：扩充提示词全程可定制、调用明细可核对、一键回退

### Incremental Delivery

1. Setup + Foundational → 基座就绪
2. US1 → 验证 → **MVP**（扩充可自定义）
3. US2 → 验证（起草可自定义——用户点名的第二处）
4. US3 → 验证（AI 辅助——降低编写门槛）
5. Polish → 契约同步 + 全量回归 + `/speckit-analyze`

### Parallel Team Strategy

单人线性 T278→T296 即可；如需并行：后端线（T279/T280/T281→T283/T284→T288→T291）与前端线（T282→T285→T286→T289→T292）可分线，T287/T290/T293 验收点合流。

---

## Notes

- `[P]` = 不同文件、无未完成依赖，可并行；`[USx]` 标签用于追溯（Setup/Foundational/Polish 不带标签）
- 测试一律先失败再实现（宪法第 I 条）；"书写即绿"任务失败即表明上游回归；golden 等价用例失败即表明默认模板被意外改动（SC-002 守护线）
- 每个任务完成即提交（提交信息含任务 ID；如 `T279: 提示词注册表——渲染/组合/校验与 legacy 逐字等价（为什么：SC-002 零回归需可自动断言的基线）`）
- 已知共享文件顺序触碰（勿并行）：`core/prompts/registry.py`（T279 → 只读引用）、`core/prompts/store.py`（T281 → T283/T284/T288/T291）、`api/routes/ai.py` 与 `tests/contract/test_ai_prompts_api.py`（T283 → T291）、`components/common/PromptEditorDialog.vue` 与 `prompt-editor-dialog.test.ts`（T285 → T292）、`AiExpandDialog.vue`（T286）、`AiContentDialog.vue`（T289；另有 005 在途改动，T278 纪律先行）
- 语义纪律（全部落于契约与 data-model）：可编辑的是业务指令模板，`{output_contract}` 槽位与固定段**永不可改**（缺失自动补尾——解析性不破坏）；辅助**不落库**、采用≠保存（FR-010）；辅助与运行同口径入 `llm_call`（含用量）；模板修改只影响其后新发起的运行；`{{...}}` 内容占位符与系统变量 `{...}` 互不侵犯
- 契约台账：contract §1~§5 测试锁定点对应 T283/T291；§6~§7 对应 T279；§8 对应 T285/T286/T289/T292；§9 的 001 契约同步归 T294
- 避免：模糊任务、同文件并行冲突、破坏故事独立性的跨故事依赖（US2/US3 仅依赖 US1 的组件接口与共享端点，不得反向依赖；golden 基准函数只存在于测试文件，生产代码不保留死路径）
