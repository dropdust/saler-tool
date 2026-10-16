# Phase 1 Data Model: AI 提示词自定义与辅助编写（扩充 / 起草）

**Feature**: `006-ai-prompt-customization` | **Date**: 2026-10-16 | 上游：[spec.md](spec.md) / [research.md](research.md)

本特性**不做数据库迁移、不新增数据表**：模板库复用既有 `app_setting` KV 表；调用留痕复用既有 `llm_call` 表（仅新增 `operation` 取值约定）。新增对象全部是**代码对象**（后端 `core/prompts/` 注册表与存取服务）与**前端展示态**。

**2026-10-16 修订（用户澄清）**：存储形态由"单份生效模板"升级为**模板库**（内置默认 + 多份具名模板 + 每功能一个生效选择）。旧单份键 `prompt_template_{feature}` **从未发布**（006 尚在实现中），直接替换为下列形状，无迁移。

---

## 1. 提示词模板库（持久化：`app_setting` 行）

| 键 | 值形状 | 语义 |
| --- | --- | --- |
| `prompt_templates_seed_expand` | `{"active_id": "<id>" \| null, "items": [{"id", "name", "content", "updated_at"}]}` | AI 扩充（`ai_seed_expand`）模板库与生效选择 |
| `prompt_templates_content_draft` | 同上 | AI 起草（`ai_content_draft`）模板库与生效选择（独立） |

- **内置默认模板**永不落库：`active_id=null`（或行不存在）即用注册表默认；不可修改、不可删除。
- `active_id` 指向 `items` 中不存在的 id（脏数据）→ 读取回落默认并视为未自定义（防脏数据外溢）。
- item：`id`（服务端生成的短随机标识）、`name`（同功能内唯一：strip 后比对）、`content`（≤8000，规则见契约 §7）、`updated_at`（ISO 字符串，服务端写）。
- 边界：名称必填 ≤60 字符；每功能 ≤50 份（满载给出明确错误）。
- 运行读取口径（`store.get_effective`）：`(生效模板内容, 是否自定义)`——签名与单模板版一致，`run_expansion`/`run_content_draft` 零改动。
- 状态机（每功能独立）：

```text
                   创建/另存为（命名）                切换（选择即生效）
  默认（active_id=null） ◀──────────────▶ 生效=某具名模板
        ▲    │                                  │
        │    │ 另存为（默认态保存引导）            │ 删除生效模板（自动回退）
        │    ▼                                  ▼
        └── items: [ 具名模板A, 具名模板B, … ]（增/改名/删，互不影响生效选择）
```

- 写入约束（创建/更新内容均适用）：空/纯空白、>8000 字符、名称缺失或重名 → 400（不改动既有数据）；未知变量/缺失变量/缺失槽位 → warnings 不阻断（规则见契约 §7）。
- 通用 `PUT /settings` 对 `prompt_templates_*` 键一律拒绝（前缀守卫沿用 T280，`prompt_template_` 前缀已覆盖复数形态）。

## 2. 提示词功能注册表（代码对象：`core/prompts/registry.py`）

### 2.1 功能定义

| feature key（= llm_call.operation） | 展示名 | 变量集 | 固定段（不可编辑） |
| --- | --- | --- | --- |
| `seed_expand` | AI 扩充（种子扩充） | `{description}` `{existing_nodes}` `{count}` | `输出 JSON，结构：\n- nodes[]: {node_type, name, attributes, confidence, rationale}\n- edges[]: {from, to, relation_type}\n- seeds[]: {query, product_line?, persona?, market?, priority, rationale}`（即现文案的 JSON 结构块） |
| `content_draft` | AI 起草（内容母版） | `{brief}` `{tone}` `{content_type}` `{language}` | `输出 JSON：{"subject": "主题行（如适用）", "body_md": "Markdown 正文"}。`（即现文案的输出行） |

两功能各自拥有：默认模板全文（由现文案机械重构，`{output_contract}` 槽位在原位置）、固定段、变量目录、长度上限（8000）、展示名。注册表为纯函数模块（不依赖 FastAPI/DB）。

### 2.2 变量渲染语义（compose 时逐 token 精确替换）

| 变量 | 渲染为 | 空值/缺省行为 |
| --- | --- | --- |
| `{description}` | `"业务描述：<表单描述>"` | `""`（表单未填） |
| `{existing_nodes}` | 按 产品线→客户角色→市场/国家 依次输出存在的行：`"已有产品线：a、b"`（\n 连接，最多 80 名/类） | `""` |
| `{count}` | 纯数字字符串（如 `"20"`） | 恒有值（表单默认 20） |
| `{brief}` | `"业务要点：<表单要点>"` | 表单必填，恒有值 |
| `{tone}` | `"语气：<表单语气>。"` | `"语气：专业、克制、以价值为先。"` |
| `{content_type}` | 主题内容类型名的纯值（如 `"开发信"`） | 恒有值 |
| `{language}` | 母版语言代码纯值（如 `"zh"`） | 恒有值 |
| `{output_contract}` | 该功能固定段原文（只读槽位） | 模板缺失时：保存警告 + 运行时自动补于末尾（`\n\n` 分隔） |

- 未知 `{token}` 原样透传（保存时警告）；`{{...}}`（内容占位符如 `{{company_name}}`）不参与扫描与替换。

### 2.3 组合管线（compose）

```text
有效模板 = 生效模板内容（active_id 指向的具名模板）│ 注册表默认模板
用户消息 = render(有效模板, 变量上下文)      # {output_contract} → 固定段原文
系统消息 = provider 既有默认（"只输出严格 JSON…"）   # 不变
```

- 运行期调用点：`run_expansion` / `run_content_draft` 开始执行时读一次、组合一次、定格到本次运行（R7）。
- **默认等价保证**：默认模板组合结果与 legacy `build_expansion_prompt` / `_build_draft_prompt` 输出逐字相等（golden 单元测试锁定，含空描述/空节点边界），SC-002 由此可回归。

## 3. AI 辅助调用（复用 `llm_call` 表，新增取值约定）

| 列 | 约定值 | 说明 |
| --- | --- | --- |
| `operation` | `prompt_assist` | 新增操作名（既有列无枚举约束） |
| `job_id` | `NULL` | 交互式调用不挂任务 |
| `phase` | `NULL` | 无循环上下文 |
| `request_messages` | `[system(辅助系统消息), user(功能+变量目录+固定段+意图/草稿)]` | 明细抽屉完整可见（FR-008/011） |
| `response_text` | `{"suggestion": "...", "notes": "..."}` 原文 | 建议不落业务库，仅随响应到编辑器 |
| `ok` / `attempt` / 修复链 | 沿用既有三态与逐次尝试契约 | 含失败/超时收口 |

- 辅助调用同时写 `operation_log` 遥测（`telemetry.record_from_provider`, operation=`prompt_assist`），口径与运行类一致。

## 4. 前端对象（展示态，不落库）

- **提示词编辑器状态**：`{feature, content(编辑中), templates(库详情), active_id, dirty, saving, assist:{mode, intent, draft, loading, suggestion, notes}}`；选择器切换即调 `PUT active`（无未保存修改时）并载入对应内容。
- **状态徽标**：对话框打开时经 `GET /ai/prompts` 取得 `customized` 与 `active_name`，呈现"默认"或生效模板名。
- **建议态**：`suggestion` 独立于编辑内容展示；"采用"写入编辑区（dirty=true）、"丢弃"清除；二者均不触发保存。
