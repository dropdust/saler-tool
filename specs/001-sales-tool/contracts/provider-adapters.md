# Contract: Provider 适配器接口（后端内部契约）

**Feature**: `001-sales-tool` | **Date**: 2026-10-10

后端对"外部能力提供方"的统一抽象：大模型（LLM）、检索（Search）、邮件发送（Mail）、短信发送（SMS）。
所有业务代码只依赖这些接口，不直接依赖任何具体 SDK/服务；具体首批提供方清单见 [research.md](../research.md) 与 [plan.md](../plan.md)。

## 通用约定

- 所有适配器为**纯 I/O 组件**：不写数据库、不做重试编排、不读写配置——由任务层（Job 层）负责重试、限速、记账。
- 统一错误分类（每种适配器都抛 `ProviderError(kind, message, retryable, provider_detail)`）：

| kind | 含义 | 任务层策略 |
|---|---|---|
| `auth` | 凭证无效/过期 | 立即失败并提示用户检查配置 |
| `quota` | 配额/额度耗尽 | 暂停任务，提示用户 |
| `rate_limit` | 被限流（含 Retry-After） | 按建议退避重试 |
| `timeout` / `network` | 网络问题 | 指数退避重试 |
| `blocked` | 被目标风控/拒答（检索特有） | 切备用渠道/降速 |
| `parse` | 页面结构变化/解析失败（网页端检索特有；004） | 立即切换下一渠道（不可重试） |
| `invalid_output` | 输出不符合 schema（LLM 特有） | 携带校验错误重试（有限次） |
| `recipient_rejected` | 收件人被拒（发送特有） | 记入台账标记失败，不重试 |
| `server` | 对端 5xx | 退避重试 |

- 凭证注入：适配器实例由"通道/提供方配置"构造，密钥经加密存储解密后仅在内存中短暂存在；日志与异常信息必须脱敏（FR-006）。

## 1. LLM 适配器

```python
class LLMProvider(Protocol):
    def test_connection(self) -> TestResult: ...
        # TestResult{ok: bool, detail: str, models: list[str] | None}

    def generate_structured(self, *, prompt: str, schema: dict,
                            system: str | None = None,
                            max_repair_attempts: int = 2,
                            timeout_s: float = 120,
                            on_attempt: Callable[[dict], None] | None = None) -> dict: ...
        # 返回通过 schema 校验的 JSON 对象（dict）。
        # 内部流程：请求 → 解析 JSON → jsonschema 校验 → 失败则把校验错误回传模型修复 → 仍失败抛 invalid_output。
        # on_attempt 逐次尝试回调（llm_call 明细）：{provider, model, attempt, messages, response_text,
        # ok, error_kind, error_detail, latency_ms, usage}；回调自身异常不得影响模型调用。

    def translate(self, *, items: list[str], source_lang: str, target_lang: str,
                  glossary: dict[str, str] | None = None,
                  timeout_s: float = 120,
                  on_attempt: Callable[[dict], None] | None = None) -> list[str]: ...
        # 等长返回；glossary 传入词表术语（产品名/行业术语）以保持多语言一致性（FR-038）。
        # on_attempt 透传给 generate_structured。

    def complete(self, *, prompt: str, system: str | None = None,
                 timeout_s: float = 120) -> str: ...
```

**结构化任务 schema（后端内置，版本化）**

- `seed_expansion_v1` —— 知识图谱扩充（FR-012①）：
  ```json
  {
    "nodes": [{"node_type": "product_line|persona|market|org", "name": "…",
               "attributes": {}, "confidence": 0.8, "rationale": "…"}],
    "edges": [{"from": "名称", "to": "名称", "relation_type": "product_fit_persona|product_target_market|org_in_market|org_has_persona"}],
    "seeds": [{"query": "中文母版检索意图", "product_line": "…", "persona": "…",
               "market": "…", "priority": 1, "rationale": "…"}]
  }
  ```
  入库规则：全部以 `review_status=pending` 落库；`seeds` 须先经 `seed.query` 唯一性过滤（FR-010）；
  种子 `query` 为中文母版（具名机构实体保留原文），落库 `lang` 固定 `zh`、不由模型决定——翻译为目标语言是审核后的独立步骤（FR-012②，`/ai/seeds/translate`）。
- `seed_translation_v1` —— 中文种子/词表翻译（FR-012/009）：`{"items": [{"source": "…", "target": "…"}]}`，逐条带语言标注。
- `content_draft_v1` —— 文案辅助编写：`{"subject": "…", "body_md": "…"}`（变量占位符 `{{…}}` 保留）。
- `content_translation_v1` —— 母版 → 目标语言版本：`{"subject": "…", "body_md": "…", "glossary_applied": ["…"]}`。

**输出可信边界**：LLM 结果一律视为"候选/草稿"，必须经人工审核（FR-012/038）；后端不得将未审核内容写入可发送状态。

## 2. 检索（Search）适配器

```python
class SearchProvider(Protocol):
    name: str  # 稳定标识，如 "brave" / "serper" / "google_cse"

    def search(self, *, query: str, count: int = 20,
               lang: str | None = None, country: str | None = None,
               timeout_s: float = 30) -> list[SearchItem]: ...
        # SearchItem{title: str, url: str, snippet: str}

    def test_connection(self) -> TestResult: ...
```

- 任务层按用户配置的**渠道优先级**调用；命中 `blocked/rate_limit` 时自动切换下一渠道（Edge Cases"检索渠道风控→切换/降速"）。
- 查询构造由种子完成；适配器不做查询改写。
- 结果去重、平台站过滤（目录站/社媒平台）在任务层完成，适配器保持简单。

**004 增量：免密钥渠道与安全失败纪律**（详见 [004 契约](../../004-search-channel-expansion/contracts/search-channel-expansion-contract.md)）：
- 类型清单（共 9）：需密钥 `brave/serper/tavily`；免密钥 `bing_html`（RSS 形态优先 + HTML 回退）、`baidu_html`（`mu` 离线还原、cookie 与 UA 配对）、`mojeek_html`、`google_html`（`/url?q=` 离线、`/goto` 跟随一次）、`wikipedia`（官方 API、描述性 UA）、`ddg_html`（既有兜底、lite 回退一次）。
- **错误矩阵增 `parse`**；**空结果纪律**：命中风控标记 → `blocked`；结构正常确无结果 → 合法空 `[]`；容器整体缺失/无法区分 → `blocked`（绝不写脏数据）。
- **链接还原通则**：包装链接一律还原为目标地址（百度 `mu`/`data-landurl`、Bing `ck/a` base64url、DDG `uddg` 离线；Google `/goto` 签名跟随一次）；不可还原 → 丢弃该条，MUST NOT 写入包装链接。
- **预置元数据**：注册 manifest 增可选 `preset`（endpoint/note/apply_url/access_mode ∈ {official_api, html}/market/risk）；`needs_key` 为派生值（`secret_fields` 非空）；`GET /search/presets` 由注册表派生。
- **运行时记账**（测试与任务同口径）：每次渠道调用尝试 `used_today` +1（按日重置）；成功 `healthy` 且清空最近失败；失败 `failing` + `last_error_kind/at`。
- **节流**：网页渠道引擎级最小间隔（默认 2.0s + 0~1.5s 抖动；渠道 `params.interval_s` 可调、≤0 显式关闭）；浏览器 UA 池轮换（百度 cookie/UA 配对；Wikipedia 描述性 UA）。

## 3. 邮件发送（Mail）适配器

```python
class MailSender(Protocol):
    def verify(self) -> TestResult: ...

    def send(self, *, message: OutgoingMail, timeout_s: float = 60) -> SendResult: ...
        # OutgoingMail{from_name, from_addr, reply_to, to, subject,
        #             body_text, body_html, headers: dict}
        # SendResult{message_id: str}

    def send_limit_hint(self) -> int | None: ...
        # 提供方建议的日上限（如有），供任务层与用户配置取最小值
```

- 发送层职责（不在适配器内）：检查 suppression/exclusion → 渲染内容版本 → 配额与节奏控制 → 写 `send_record`。
- 试发（FR-053）与正式发送走同一接口，仅目标不同。

## 4. 短信发送（SMS）适配器

```python
class SMSSender(Protocol):
    def verify(self) -> TestResult: ...

    def send(self, *, phone_e164: str, text: str,
             signature: str | None = None, timeout_s: float = 30) -> SendResult: ...
```

- 首批支持的服务商与配置形态见 research.md；统一以"HTTP API + 用户自备凭证"接入。

## 5. 通道健康与注册表

- 每类适配器实现向 **Provider Registry** 注册：`{type_key, display_name, config_schema(JSON Schema), secret_fields[], factory, preset?}`（`preset` 为 004 增量：渠道预置元数据）。
- 前端通过 `GET /api/v1/<类别>/providers` 读取 `config_schema` 动态渲染配置表单（这样新增提供方无需改前端）。
- `POST /…/{id}/test` 统一映射到适配器的 `test_connection()/verify()`。

## 6. 新增提供方的检查单

1. 实现对应 Protocol；2. 注册 manifest（type_key、config_schema、secret_fields）；3. 提供 fixture 级联调（不依赖真实凭证的假实现）；4. 明确错误分类映射；5. 在 research.md"后续可接入"清单中登记候选；6. 检索网页解析型渠道（004）：实现 `_check_blocked`/`_results_container_present` 安全失败纪律，并提供 `preset`（风险提示必填）。
