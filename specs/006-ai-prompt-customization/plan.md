# Implementation Plan: AI 提示词自定义与辅助编写（扩充 / 起草）

**Branch**: `006-ai-prompt-customization` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-ai-prompt-customization/spec.md`

## Summary

为「AI 扩充」与「AI 起草」开放提示词能力：每功能内置默认业务指令模板 + **多份具名自定义模板（模板库，任选一份当前生效；2026-10-16 用户澄清修订，见 research R9）**；零配置开箱即用，默认组合输出与现状**逐字一致**并以 golden 单测锁定；模板经 `{变量}` 注入表单数据、经 `{output_contract}` 保留槽位内嵌系统固定的输出结构段（用户不可改，缺失时运行时自动补尾——解析性永不破坏）。模板库持久化复用 `app_setting` KV（备份/导出天然覆盖，**无数据库迁移**）。编辑器内提供 AI 辅助（生成/润色建议，建议态、采用≠保存），辅助调用同步执行并以 `operation="prompt_assist"`、`job_id=NULL` 落既有 `llm_call` 明细，与运行类调用同口径透明。运行侧 `run_expansion`/`run_content_draft` 改为"注册表默认 + 生效模板覆盖 + 组合渲染"纯函数管线（`core/prompts/`），任务开始执行时读取一次、定格本次运行。

## Technical Context

**Language/Version**: Python ≥3.12（后端）｜ TypeScript 5.x + Vue 3（前端）

**Primary Dependencies**: FastAPI + SQLAlchemy（SQLite）｜Element Plus + Pinia + Vue Router；LLM 复用既有 `OpenAICompatibleProvider`（**零新增依赖**）

**Storage**: 复用 `app_setting` KV（`prompt_template_seed_expand` / `prompt_template_content_draft`，行存在=已自定义）；调用留痕复用 `llm_call`（新增 `operation="prompt_assist"` 取值）；无迁移

**Testing**: 后端 pytest（unit / contract / integration，FakeLLMProvider 离线可跑）；前端 vitest + @vue/test-utils（Element Plus + mock api 客户端）

**Target Platform**: 三平台桌面应用（pywebview 壳 + 本地 HTTP API；离线可用，编辑器/保存不依赖网络）

**Project Type**: 桌面应用（frontend + backend 双工程，单仓库）

**Performance Goals**: 编辑器加载/保存 <300ms（本地 KV）；AI 辅助常规网络 ≤30s 返回（硬上限 60s，SC-005）；保存校验即时（纯函数规则）

**Constraints**: 模板上限 8000 字符；默认路径提示词逐字等价（SC-002 回归口径）；辅助必须落调用明细（FR-011）；未配置模型时编辑器全功能可用、辅助给出配置指引（FR-012）

**Scale/Scope**: 单用户本机；2 功能 × 1 模板；新增 ≈4 个 API 端点 + 1 个后端领域模块 + 1 个前端共享组件

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则/条款 | 检查结论 |
| --- | --- |
| **I 测试驱动（不可协商）** | 每任务红→绿：注册表渲染/golden 等价、校验警告、端点契约（含辅助落明细与 409）、两对话框入口与编辑器交互，全部先写失败测试；离线可跑（FakeLLMProvider）。✅ |
| **II 面向对象与封装** | 提示词注册表为 `core/` 领域纯函数模块（禁 FastAPI/DB 依赖，设置读写经 `settings_service`）；API 面挂既有 `/ai` 路由；前端编辑器为 `components/common/` 共享组件，只依赖本文件约定的 API 契约。✅ |
| **III 约定大于配置** | 默认模板开箱即用、不配置零差异；新端点沿用既有错误包与路径约定；契约按 §9 同步 001 `local-api.md`。✅ |
| **IV 技术栈限定** | 不引入新语言/框架/依赖（无模板引擎、无新库）。✅ |
| **V 密钥零入库** | 辅助调用走用户已配置 provider（运行时解析）；模板为业务文本非凭证，无新密钥面。✅ |
| **附加约束·数据主权** | 辅助与运行均由用户主动触发、入调用明细可审计（含完整入参出参）；编辑器内明示"模板将随调用发送"；无隐藏外发。✅ |
| **附加约束·演进兼容** | 注册表按 feature key 可扩展（翻译等其他 AI 能力日后加一行注册即可）。✅ |

**Post-Phase 1 re-check（设计后复评）**：Phase 1 产物（[data-model.md](data-model.md) / [contracts/](contracts/prompt-customization-contract.md) / [quickstart.md](quickstart.md)）未引入新依赖、新表、新密钥面或跨层依赖；`{output_contract}` 槽位与 golden 等价保证 SC-002 可自动回归。**结论：通过，无违反项**。

## Project Structure

### Documentation (this feature)

```text
specs/006-ai-prompt-customization/
├── plan.md              # 本文件
├── spec.md              # 规格（/speckit-specify 产出）
├── research.md          # Phase 0：R1~R8 决策记录
├── data-model.md        # Phase 1：持久化与状态语义
├── quickstart.md        # Phase 1：V1~V4 验证指南
├── contracts/
│   └── prompt-customization-contract.md   # Phase 1：端点/校验/渲染/前端呈现契约
├── checklists/
│   └── requirements.md  # 规格质量检查单（16 项全过）
└── tasks.md             # Phase 2 产出（/speckit-tasks，非本命令）
```

### Source Code (repository root)

```text
backend/
├── src/saler/
│   ├── core/prompts/
│   │   ├── __init__.py
│   │   ├── registry.py            # 功能注册表：默认模板/固定段/变量元数据/渲染语义/组合/校验（纯函数）
│   │   └── assist.py              # AI 辅助：辅助提示词构建 + 经 provider 调用（同步路由调用点）
│   ├── core/seeds/ai.py           # run_expansion：改经 registry 组合（读设置覆盖，替代硬编码 build_expansion_prompt）
│   ├── core/content/ai.py         # run_content_draft：同上（替代 _build_draft_prompt）
│   ├── api/routes/ai.py           # + GET /ai/prompts、GET/PUT /ai/prompts/{feature}、POST …/reset、POST …/assist
│   ├── api/routes/settings.py     # 通用 PUT /settings 拒绝 prompt_template_* 键
│   ├── services/settings_service.py   # + delete_value（恢复默认=删行）
│   └── providers/llm/schemas.py   # + PROMPT_ASSIST_V1_SCHEMA（{suggestion, notes}）
└── tests/
    ├── unit/test_prompt_registry.py        # 渲染语义/golden 等价/校验警告/槽位兜底
    ├── contract/test_ai_prompts_api.py     # §1~§5 端点契约 + llm_call 落行 + 409 门控
    └── unit/test_seed_ai.py 等更新          # 自定义模板在运行中生效的断言

frontend/
├── src/components/common/PromptEditorDialog.vue   # 共享编辑器（模板/变量面板/只读固定块/辅助区）
├── src/views/seeds/AiExpandDialog.vue             # +「提示词」入口与默认/已自定义徽标
├── src/views/content/AiContentDialog.vue          # 起草页签 + 同款入口
├── src/api/types.ts                               # 模板详情/列表/警告类型
└── tests/
    ├── prompt-editor-dialog.test.ts               # 编辑器交互（保存预检/恢复/建议采用/409 指引）
    └── ai-expand-calls-entry.test.ts 等增补        # 两对话框入口与徽标
```

**Structure Decision**: 沿用 001 规划的前后端双工程结构（backend `src/saler/{core,api,services,providers}` 分层 + frontend `src/{views,components,api}`）。提示词领域逻辑落在 `core/prompts/`（宪法 II：core 不直接依赖 FastAPI；设置访问经 `services/settings_service`）；API 增量挂在既有 `/ai` 路由（宪法 III：约定路径）；前端编辑器做成 `components/common/` 共享组件供两处对话框复用（与 `LlmCallsDrawer`/`JobRunPanel` 同层）。

## Complexity Tracking

> 无违反项——本特性未引入新项目、新依赖、新表或跨层访问，无需豁免。
