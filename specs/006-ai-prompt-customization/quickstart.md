# Quickstart: AI 提示词自定义与辅助编写（扩充 / 起草）

**Feature**: `006-ai-prompt-customization` | **Date**: 2026-10-16

本文件是**验证指南**：如何运行本特性并按用户故事逐条验证。数据形状见 [data-model.md](data-model.md)；接口约定见 [contracts/prompt-customization-contract.md](contracts/prompt-customization-contract.md)；通用环境前提（安装、打包、数据目录）与 001 quickstart §1–§3 一致，真实运行验收沿用 005 拟定的本机验收配方（构建产物 + `--server` + 临时数据目录 + headless Chrome CDP 真实点击流）。

## 1. 运行与测试

```bash
# 开发形态（后端 + 前端 dev）
cd backend && uv run uvicorn saler.api.dev:app --reload --port 8620
cd frontend && pnpm dev                                   # http://localhost:5173

# 验收形态（构建产物 + 无窗服务 + headless Chrome CDP，沿用本机验收配方）
cd frontend && pnpm build
cd backend && SALER_DATA_DIR=/tmp/saler-accept-006 uv run python -m saler.desktop --server --port 8620

# 自动化测试（离线可跑；LLM 一律 FakeLLMProvider，无真实外网依赖）
cd backend && uv run pytest tests/unit/test_prompt_registry.py tests/unit/test_seed_ai.py \
    tests/contract/test_ai_prompts_api.py
cd frontend && pnpm test && pnpm lint                     # prompt-editor-dialog + 两对话框入口 + 全量
```

> **前提声明**：V1–V3 的真实运行需要已配置的大模型服务（设置 → 大模型）；不可达时以假 Provider/离线样本走自动化层验证。V3 的 AI 辅助属真实外发调用（用户主动触发、入调用明细）。

## 2. 验证场景

### V1 自定义扩充提示词端到端（US1 / FR-001~008、014/015 / SC-001~004；模板库版 2026-10-16 修订）

前置：已配置大模型服务；种子库/图谱有若干节点。步骤：① 打开「AI 扩充」对话框，核对「提示词」入口与「默认」徽标；② 打开编辑器——核对默认模板全文、模板选择器（当前=「内置默认」）、变量面板（业务描述/已有节点/候选数量，含"将被替换为…"说明）、`{output_contract}` 槽位处的固定块只读呈现、长度额度（0/8000 起算）；③ 在模板中加入可辨认指令（如"候选机构必须包含行业展会与行业协会类别"）→「另存为」命名"东非市场"（创建即生效，≤3 次操作）；④ 核对徽标与选择器显示「东非市场」、编辑器内容回显；⑤ 发起一次扩充（填写描述、选节点、数量），完成后「查看调用明细」：核对 user 消息 = 所存模板内容且 `{description}`/`{existing_nodes}`/`{count}` 已替换为本次表单值、`{output_contract}` 处为固定结构段原文、系统消息仍为 JSON 守门；核对产出进入待审核且体现新增指令；⑥ 再「另存为」"展会渠道"（内容再作区分）→ 在选择器切回「东非市场」（选择即生效）→ 核实徽标同步 → 发起第二次扩充核对明细用东非版；⑦ 重命名"东非市场"→"东非-电力"核对生效；⑧ 删除"东非-电力"（二次确认）→ 核对自动回退「默认」且"展会渠道"仍在库中；⑨ 选择「内置默认」（=切回默认，已存模板保留）→ 再发起一次扩充核对明细用默认模板。预期：SC-001/003/004 达成；页内提示语言（"发送至已配置的大模型服务"）与实际一致。

**边界抽查（FR-005/015 阻断与警告）**：模板写 `{descriptoin}`（拼错）→ 保存后响应/提示列出 `unknown_variable`；删除 `{description}` 引用 → `missing_variable`；删除 `{output_contract}` → `missing_output_contract` 且运行明细末尾自动补结构段；清空模板 → 400"提示词不能为空"；粘贴 8001 字符 → 400 且提示额度；同名另存为 → 400 重名提示；「默认」态直接保存 → 引导另存为（命名后创建并生效，不覆盖默认）；运行中切换/删除模板 → 在途运行明细不受影响。

### V2 自定义起草提示词（US2 / FR-001~003、007、014）

前置：内容主题 1 个（已有或新建）。步骤：① 打开「AI 内容辅助」→「起草/润色母版」页签，核对「提示词」入口徽标；② 编辑器核对默认模板、模板选择器、变量面板（业务要点/语气/内容类型/语言）；③ 加入可辨认写作约束（如"正文首段必须以一句话概括价值主张"）另存为具名模板并生效；④ 发起起草（要点+语气）→ 明细核对 user 消息为该模板、`{brief}`→"业务要点：…"、`{tone}` 有值/缺省两态渲染语义正确、`{{company_name}}`/`{{signature}}` 未被误替换；⑤ 核对扩充模板库与生效选择不受影响（两功能独立）；⑥ 切回默认核对还原且起草模板保留。

### V3 AI 辅助编写（US3 / FR-009~012 / SC-005/006）

前置：已配置大模型服务。步骤：① 编辑器内输入意图（"面向东非市场，重点发掘各国电力公司与 EPC 总包"）→「AI 生成」→ 核对 ≤60s（常规 ≤30s）出现建议全文与 notes、请求期间编辑器可继续编辑；② 核对编辑器原文与已保存模板均未变；③「采用」→ 建议进入编辑器（dirty）→ 关闭不保存 → 重开核对已保存模板未变（采用≠保存）；④「丢弃」核对编辑器原内容不变；⑤ 对已写草稿「AI 优化」核对建议对照呈现；⑥ 编辑器内「查看调用明细」按 `operation=prompt_assist` 核对本次辅助的完整入参与 `{suggestion, notes}` 出参、用量；⑦ 断开/清空模型配置再试 → 409 提示与「设置 → 大模型」指引，编辑器内容无损。

**降级路径自动化**：`tests/contract/test_ai_prompts_api.py` 以 FakeLLMProvider 离线断言 ①②③⑤⑥⑦ 的服务端行为与 llm_call 落行。

### V4 默认等价回归（SC-002）

步骤：不打开编辑器、不自定义，走一次扩充与一次起草（或跑 `tests/unit/test_prompt_registry.py` 的 golden 用例：代表性上下文含空描述/空节点）→ 核对组合后的提示词与升级前构建函数输出**逐字相等**、结果流向（待审核草稿）与运行体验无差异。

## 3. 验收结论

（待实现阶段回填：各 V 场景实测结果、发现问题与修复、全量测试统计。）
