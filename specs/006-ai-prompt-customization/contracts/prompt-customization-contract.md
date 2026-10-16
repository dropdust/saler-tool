# Phase 1 Contract: AI 提示词自定义与辅助编写——模板、校验与辅助调用约定

**Feature**: `006-ai-prompt-customization` | **Date**: 2026-10-16 | 关联：[local-api.md](../../001-sales-tool/contracts/local-api.md)（§AI 节按 §9 同步增补）与 [prompt-customization 数据模型](../data-model.md)

本文件定义本特性的接口增量：模板读取/保存/恢复、AI 辅助、校验与警告码表、组合渲染与前端呈现约定。**全部为新增端点**（不改动既有端点行为）；错误一律沿用 `{code, message, details}` 包。

---

## 1. `GET /api/v1/ai/prompts`（模板状态列表）

| 项 | 约定 |
| --- | --- |
| 用途 | 两个对话框打开时取状态徽标 |
| 响应 | `{ "items": [ {feature, label, customized, updated_at} ] }`，恰 2 项，顺序固定 `seed_expand` → `content_draft` |

```jsonc
// → 200
{ "items": [
  { "feature": "seed_expand", "label": "AI 扩充（种子扩充）", "customized": true,  "updated_at": "2026-10-16T09:12:00" },
  { "feature": "content_draft", "label": "AI 起草（内容母版）", "customized": false, "updated_at": null }
] }
```

## 2. `GET /api/v1/ai/prompts/{feature}`（模板详情）

| 项 | 约定 |
| --- | --- |
| `{feature}` 未知 | **404 `not_found`** |
| 响应 | 编辑器全量数据（含默认模板供对照/恢复） |

```jsonc
// GET /api/v1/ai/prompts/seed_expand → 200
{
  "feature": "seed_expand",
  "label": "AI 扩充（种子扩充）",
  "content": "你是 B2B 外贸获客的市场调研助手。……{description}\n{existing_nodes}\n{output_contract}\n要求：seeds 约 {count} 条……",
  "default_content": "……（内置默认模板全文，含 {output_contract} 槽位）",
  "customized": true,
  "updated_at": "2026-10-16T09:12:00",
  "max_length": 8000,
  "variables": [
    { "name": "description",     "label": "业务描述",   "render": "有值 →「业务描述：…」；未填 → 空" },
    { "name": "existing_nodes",  "label": "已有节点名单", "render": "按产品线/客户角色/市场逐行「已有X：A、B」；无 → 空" },
    { "name": "count",           "label": "候选数量",   "render": "纯数字（表单值）" }
  ],
  "output_contract": "输出 JSON，结构：\n- nodes[]: ……",
  "reserved_variables": [
    { "name": "output_contract", "label": "输出结构槽位", "render": "替换为上方固定段原文（不可修改；缺失时运行时自动补于末尾）" }
  ]
}
```

- `variables` 与 `reserved_variables` 的区分即"可编辑数据变量"与"保留槽位"；`render` 文本直接展示给用户（"将被替换为…"）。
- `content_draft` 的 `variables` 为 `brief / tone / content_type / language`，`output_contract` 为输出行原文。

## 3. `PUT /api/v1/ai/prompts/{feature}`（保存模板）

| 项 | 约定 |
| --- | --- |
| 请求 | `{ "content": "<模板文本>" }` |
| 成功 | **200**：响应 = 详情形状（§2）+ `"warnings": [ {code, message} ]`；`customized` 置 `true` |
| 阻断 | 空/纯空白 → **400 `bad_request`**「提示词不能为空」；> `max_length` → **400 `bad_request`**（消息含额度与当前长度）；未知 feature → 404 |
| 警告 | 见 §7 码表；**不阻断**，随成功响应返回，前端在保存后照常提示 |
| 持久化 | 写 `app_setting[prompt_template_{feature}] = {"content": …}`（行不存在则插入） |
| 生效范围 | 仅其后新发起的运行；进行中的运行不受影响（FR-007） |

```jsonc
// PUT /api/v1/ai/prompts/seed_expand  {"content": "你是……{count}……"} → 200（节选）
{ "feature": "seed_expand", "customized": true, "content": "……",
  "warnings": [
    { "code": "missing_output_contract", "message": "未包含 {output_contract} 输出结构槽位：运行时会自动补充在末尾" },
    { "code": "missing_variable", "message": "未引用 {description}：表单中的业务描述将不再发送给模型" }
  ] }
```

## 4. `POST /api/v1/ai/prompts/{feature}/reset`（恢复默认）

| 项 | 约定 |
| --- | --- |
| 请求体 | 无 |
| 成功 | **200**：详情形状（§2），`customized=false`、`content=default_content`、`updated_at=null`；实现 = 删除 `app_setting` 行 |
| 语义 | 立即生效：下一次运行即用默认模板；编辑器同步呈现默认内容 |
| 幂等 | 对已是默认的功能再次调用同样返回 200（无副作用） |

## 5. `POST /api/v1/ai/prompts/{feature}/assist`（AI 辅助编写）

| 项 | 约定 |
| --- | --- |
| 请求 | `{ "mode": "generate" \| "polish", "intent": "…", "draft": "…" }`：`generate` 必填 `intent`（非空 ≤2000）；`polish` 必填 `draft`（非空 ≤8000）；`mode` 非法或必填缺失 → **400 `bad_request`** |
| 成功 | **200** `{ "suggestion": "<候选模板全文>", "notes": "<修改要点/说明，可为 null>" }` |
| 未配置服务 | **409 `llm_not_configured`**（既有码；前端呈现前往「设置 → 大模型」的指引） |
| 执行 | 同步调用默认 LLM 服务（浏览器等待），`timeout_s=60, deadline_s=60`，结构化输出 `PROMPT_ASSIST_V1_SCHEMA={suggestion, notes}`，复用修复重试管线 |
| 记录 | `llm_call`：`operation="prompt_assist"`、`job_id=NULL`、`phase=NULL`，逐次尝试含 `request_messages/response_text/usage`（FR-011）；另写 operation_log 遥测 |
| 建议态 | 服务端**不落库**建议；"采用/丢弃"纯前端行为，"采用"≠保存（FR-010） |

```jsonc
// POST /api/v1/ai/prompts/seed_expand/assist
{ "mode": "generate", "intent": "面向东非市场，重点发掘各国电力公司与 EPC 总包，保留中文母版表述" }
// → 200
{ "suggestion": "你是 B2B 外贸获客的市场调研助手……{description}\n{existing_nodes}\n{output_contract}\n要求：seeds 约 {count} 条……重点覆盖东非各国电力公司与 EPC 总包……",
  "notes": "强化了东非市场与机构类型的措辞；保留全部变量与输出结构槽位" }
```

## 6. 变量、槽位与组合渲染（权威语义）

| 项 | 约定 |
| --- | --- |
| 变量语法 | `{name}`；渲染为**已知名**的精确 token 替换；未知 `{token}` 原样透传 |
| 豁免 | `{{...}}`（内容占位符 `{{company_name}}`/`{{signature}}`）既不扫描也不替换 |
| `{output_contract}` | 保留槽位 → 替换为该功能固定段原文；模板缺失槽位时运行期自动补于末尾（`\n\n` 分隔），解析性永不破坏（FR-004） |
| 组合 | 用户消息 = 渲染(有效模板)；系统消息 = provider 既有默认，不变 |
| 渲染语义表 | 见 [data-model.md §2.2](../data-model.md)（`{tone}` 无值 →「语气：专业、克制、以价值为先。」等） |
| 默认等价 | 默认模板的渲染结果与升级前构建函数输出**逐字相等**（golden 单测锁定；SC-002 回归口径） |

## 7. 校验与警告码表（PUT 响应 `warnings[]`）

| code | 触发 | message 要点 |
| --- | --- | --- |
| `unknown_variable` | 出现非已知变量、非保留槽位、非 `{{...}}` 的 `{token}`（去重逐一列出） | 该处将按原文发送，建议改名或删除 |
| `missing_variable` | 任一已知数据变量未被引用（逐一列出） | 对应表单内容将不再发送给模型 |
| `missing_output_contract` | 模板未包含 `{output_contract}` | 运行时会自动补充在末尾 |

- 阻断项（空、超长）不产生 warnings——直接 400。
- 前端保存前用同一规则预检（变量元数据随 §2 下发），有警告先弹"仍要保存/取消"确认。

## 8. 前端呈现约定（实现契约）

| 项 | 约定 |
| --- | --- |
| 入口 | AI 扩充对话框、AI 起草（起草/润色母版页签）各增「提示词」入口；入口旁徽标显示「默认 / 已自定义」（`GET /ai/prompts`，对话框打开时取） |
| 编辑器 | 共享组件：模板文本域（实时长度/剩余额度）、变量面板（名称+渲染语义，可点击插入光标处）、固定段只读块（在槽位位置呈现"此处将替换为…"）、保存 / 恢复默认（二次确认）/ 关闭（脏状态确认放弃） |
| 状态呈现 | 标题旁「默认 / 已自定义」；恢复默认确认后即刷新为默认全文 |
| 保存流 | 预检警告 → 确认框 → PUT → 成功提示 + 响应 warnings（若有）逐条以 warning 提示；失败走统一错误包 |
| AI 辅助区 | 意图输入 +「AI 生成」；对当前草稿「AI 优化」；请求期间 loading 且不影响文本编辑；建议区展示 `suggestion` 全文与 `notes`，「采用 / 丢弃」；**绝不自动写入或保存** |
| 辅助追溯 | 辅助完成后提供「查看调用明细」（抽屉 `operation=prompt_assist`），与运行类明细同呈现 |
| 未配置指引 | assist 409 `llm_not_configured` → 编辑器内提示 + 跳转「设置 → 大模型」；编辑器查看/编辑/保存不受影响（FR-012） |
| 数据范围提示 | 编辑器含既有风格提示：模板文本将随每次运行发送至已配置的大模型服务 |

## 9. `local-api.md` 同步说明

本契约 §1–§5 四个新增端点（`GET /ai/prompts`、`GET/PUT /ai/prompts/{feature}`、`POST …/reset`、`POST …/assist`）与 `llm_call.operation` 新取值 `prompt_assist` 由 `/speckit-tasks` 生成"契约同步"任务增补至 001 `local-api.md` 的 §AI 节；不修改既有行。
