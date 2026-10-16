# Phase 0 Research: AI 提示词自定义与辅助编写（扩充 / 起草）

**Feature**: `006-ai-prompt-customization` | **Date**: 2026-10-16 | 上游：[spec.md](spec.md)

本文件收敛全部技术未知项，无遗留 `NEEDS CLARIFICATION`。现状基线：`core/seeds/ai.py:build_expansion_prompt`、`core/content/ai.py:_build_draft_prompt` 硬编码模板；`providers/llm/openai_compatible.py` 以固定系统消息（"只输出严格 JSON…"）+ 用户消息（构建的 prompt）发请求；`llm_call` 明细逐次记录 `request_messages` 原文（用户已在扩充调用明细中看到 system/user 两部分）。

---

## R1 模板持久化：复用 `app_setting` KV，每功能一键

**Decision**: 每个功能一个 `app_setting` 行，键 `prompt_template_seed_expand` / `prompt_template_content_draft`，值 `{"content": "<模板文本>"}`。**行存在 = 已自定义**；恢复默认 = 删除该行（`settings_service` 新增 `delete_value`）。运行期读取经 `settings_service.get(db, key, None)`，无行即用注册表默认。

**Rationale**:
- `app_setting` 是既有的应用设置 KV（`services/settings_service.py`），备份/导出（`services/export_all.py` 已含 `AppSetting`）天然携带模板——数据主权与"恢复备份即恢复提示词"零成本达成，**无数据库迁移**；
- 行存在性即"自定义"状态，`updated_at` 即"最后修改时间"，无需额外字段；
- 单用户单模板，KV 的复杂度恰到好处。

**Alternatives considered**:
- 新建 `prompt_template` 表：为 2 行数据引入迁移与新仓储，违反"约定大于配置"；否。
- 存数据目录文件：绕过备份/导出与事务，游离于既有设置体系；否。
- 单个键存全部功能：行级"已自定义"判定与局部更新变复杂；否。

**附加守卫**: 通用 `PUT /settings` 拒绝 `prompt_template_` 前缀键（`bad_request`），防止绕过专用端点的校验写入脏形状；`GET /settings` 对新增键的透出无害，不另行处理。

## R2 变量语法：单花括号精确 token 替换 + `{{...}}` 豁免

**Decision**: 模板变量语法为 `{name}`（如 `{description}`）。渲染 = 对**已知变量名**做精确 token 替换（`str.replace`），不做格式化引擎；未知变量扫描正则带负向断言 `(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})`，**跳过 `{{...}}`**（保护文案占位符 `{{company_name}}`、`{{signature}}`——它们是产品渲染变量，出现在起草默认模板里）。

**Rationale**:
- 起草模板文本天然含 `{{company_name}}`，双花括号语法会直接冲突；
- `str.format` 遇到用户文本中的任意 `{`/`}` 即抛异常，且允许属性访问等危险表达式——不可用；
- 精确 token 替换语义可预测：只替换我们认识的 token，其余原样透传。

**Alternatives considered**:
- Jinja2/模板引擎：为 5~8 个简单占位引入重依赖，违反技术栈限定；否。
- `{{var}}` 双花括号作为系统变量：与内容占位符正面冲突；否。
- 不给用户变量、数据固定追加：不满足 FR-003（用户在模板中安排数据位置）；否。

## R3 可编辑边界与固定段：`{output_contract}` 保留槽位

**Decision**: 机器解析依赖的输出约定（扩充：`输出 JSON，结构：nodes[]/edges[]/seeds[]` 块；起草：`输出 JSON：{"subject"…,"body_md"…}。` 行）放在**固定段**中，模板以保留变量 `{output_contract}` 占位引用；组合渲染时以固定段原文替换该 token。默认模板把槽位放在与现文案完全一致的位置。模板缺失该 token：保存时警告，运行时**自动补于末尾**（FR-004 的兜底，保证可解析性永不破坏）。系统消息（"只输出严格 JSON…"）保持 provider 既有默认，不纳入可编辑面。

**Rationale**:
- 用户在编辑器里看到固定块的确切位置与内容（编辑器把该 token 渲染为只读块），既不误删也无需读文档；
- 兜底追加策略保证任何编辑组合下 JSON 结构约定都在最终提示词里存在；
- 起草的"占位符使用说明"（`{{company_name}}`/`{{signature}}` 句）保留在**可编辑**区——它是模型写作提示，删掉只会降低占位符采用率，不会破坏解析（正文仍是字符串）；价位/交期等业务约束同样可编辑，符合"业务指令开放"的本意。

**Alternatives considered**:
- 固定段一律追加末尾：可行但默认组合与现文案行序不同，失去逐字回退保证（见 R4）；且用户无法在语义位置上放置结构说明；否。
- 结构约定留在可编辑区仅加警示：一次误删即产出不可解析，违反 FR-004；否。
- 放进系统消息：改写 provider 全局行为、影响翻译等其他操作，且用户不可见其约束范围；否。

## R4 默认兼容：默认模板 + 精确组合 = 现状文案**逐字一致**

**Decision**: 两份内置默认模板由现文案机械重构而成——现固定部分抽出为固定段，其余按原顺序落入模板、动态数据处换成变量 token；组合规则 = 渲染(template) 后将 `{output_contract}` 替换为固定段原文。**以单元测试（golden）断言：对代表性上下文（含空描述、空节点等边界），默认组合结果与 legacy 构建函数输出逐字相等**。legacy 函数保留为测试基准后移除或作为 `_legacy_*` 测试夹具（实现细节由 tasks 决定，验收口径以等值为准）。

**Rationale**:
- SC-002"未自定义用户发送内容无差异"从"尽力保持"升级为**可回归证明的字节级等价**（扩充与起草均达成，得益于 R3 槽位原位）；
- 变量渲染语义精确复现现状：`{description}`→`""` 或 `"业务描述：X"`；`{existing_nodes}`→`""` 或按产品线/客户角色/市场逐行 `"已有X：a、b"`；`{count}`→纯数字；`{brief}`→`"业务要点：X"`；`{tone}`→`"语气：X。"` 或 `"语气：专业、克制、以价值为先。"`；`{content_type}`/`{language}`→纯值。变量面板逐条展示"将被替换为…"说明。

**Alternatives considered**:
- 语义等价、允许行序微调：SC-002 验收含糊，回归无从自动断言；否。
- 双轨（默认走旧函数、自定义走新管线）：两条路径长期漂移；否。

## R5 AI 辅助执行路径：同步路由（线程池）+ 独立时限，落明细不入 job

**Decision**: `POST /ai/prompts/{feature}/assist` 做**同步 `def` 路由**（FastAPI 线程池执行，与 `/llm/providers/{id}/test` 同模式），调用 `provider.generate_structured`（`PROMPT_ASSIST_V1_SCHEMA`：`{suggestion, notes}`，复用既有校验/修复重试管线），`timeout_s=60, deadline_s=60`（SC-005 的 30s 为常规预期，60s 为硬上限）。记录：`CallRecorder(session_factory, job_id=None, operation="prompt_assist")` 逐次尝试落 `llm_call`（start/finish 两态，明细抽屉已支持按 operation 过滤）；`telemetry.record_from_provider` 同步记账。

**Rationale**:
- 编辑器里的交互式短操作，用户盯着看结果；job 机制（台账、SSE、任务中心）徒增等待与噪音，且"辅助"不是长任务；
- 明细/遥测复用既有回调契约（适配器无 DB 依赖），零新面；
- 未配置服务时 `resolve_llm_provider` 抛既有 `LLMNotConfigured`（409 `llm_not_configured`），前端据此指引"设置 → 大模型"，与扩充/起草门控同口径。

**Alternatives considered**:
- 走 job + 前端 waitFor：交互路径多一轮 SSE 编排，收益为零；否。
- 前端直连服务商：绕过后端密钥与明细体系，违反架构与数据主权；否。

## R6 校验与警告：后端权威、前端同规则预检

**Decision**: 共享校验规则（`core/prompts/registry.validate_template`）：
- **阻断（400 `bad_request`）**：空/纯空白（"提示词不能为空"）；超过上限 8000 字符（消息含额度）。
- **警告（不阻断，随 PUT 响应 `warnings[]` 返回，码表见契约）**：`unknown_variable`（逐一列出，说明按原样发送）；`missing_variable`（任一已知数据变量未被引用 → 说明对应表单内容将不发送）；`missing_output_contract`（运行时自动补在末尾）。
前端保存前用同规则做客户端预检（变量元数据随 GET 下发），有警告弹确认框（"仍要保存"），确认后 PUT；后端响应警告照常展示（防御纵深）。

**Rationale**: 规则只有一份（后端实现），前端预检是为体验（不打断、可取消）；单机工具无需担心规则被绕过，但仍以服务端为准。

**Alternatives considered**: 全客户端校验（服务端无防线）；全服务端（先保存再提示，用户需二次修正）；均否。

## R7 运行期读取时机：任务开始执行时读一次

**Decision**: `run_expansion` / `run_content_draft` 在开始执行（进入任务函数）时经 `settings_service` 读取一次有效模板并组合渲染；此后本次运行的提示词定格。进行中任务不受编辑影响（FR-007），最终事实以 `llm_call.request_messages` 为准（FR-008）。

**Rationale**: "下一次新发起的运行生效"的最小实现即"运行开始读"；排队期竞态（提交后立刻改模板）在同一秒级窗口内无用户可见差异。任务参数（job.params）不增字段——明细已承载完整提示词，避免双源。

**Alternatives considered**: 提交时（路由层）快照进 job.params（数据冗余、恢复备份后参数与模板双源）；每次调用循环重读（翻译类多调用场景不属本期）。均否。

## R8 辅助提示词与建议形态

**Decision**: 辅助系统消息（固定）声明角色与纪律；用户消息携带：功能名、变量目录（名称+渲染语义+示例）、固定段原文（"不得重复或修改"）、模式参数（`generate`：用户意图句；`polish`：当前草稿全文）、输出要求（结构化 JSON：`suggestion` = 完整候选模板文本、`notes` = 修改要点）。建议**不入库**——仅随 HTTP 响应到编辑器；"采用"仅写入编辑器内存，用户点保存才落 `app_setting`。辅助请求参数（intent/draft）本身会随 `llm_call.request_messages` 留痕，满足 FR-011。

**Rationale**: 单轮单建议（spec Assumptions），schema 化输出复用修复重试；建议不落库避免"半成品状态"，与 spec FR-010 完全一致。

**Alternatives considered**: 多建议/多轮：超出 spec 范围；建议落库草稿态：多一套生命周期，无需求支撑；否。

---

**收敛结论**: 全部未知项已决策；无新增依赖、无数据库迁移；核心新对象为 `core/prompts/` 注册表（纯函数）+ 编辑器组件；默认路径字节级等价有 golden 测试兜底。
