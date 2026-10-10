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
                            timeout_s: float = 120) -> dict: ...
        # 返回通过 schema 校验的 JSON 对象（dict）。
        # 内部流程：请求 → 解析 JSON → jsonschema 校验 → 失败则把校验错误回传模型修复 → 仍失败抛 invalid_output。

    def translate(self, *, items: list[str], source_lang: str, target_lang: str,
                  glossary: dict[str, str] | None = None,
                  timeout_s: float = 120) -> list[str]: ...
        # 等长返回；glossary 传入词表术语（产品名/行业术语）以保持多语言一致性（FR-038）。

    def complete(self, *, prompt: str, system: str | None = None,
                 timeout_s: float = 120) -> str: ...
```

**结构化任务 schema（后端内置，版本化）**

- `seed_expansion_v1` —— 知识图谱扩充（FR-012）：
  ```json
  {
    "nodes": [{"node_type": "product_line|persona|market|org", "name": "…",
               "attributes": {}, "confidence": 0.8, "rationale": "…"}],
    "edges": [{"from": "名称", "to": "名称", "relation_type": "product_fit_persona|product_target_market|org_in_market|org_has_persona"}],
    "seeds": [{"query": "…", "lang": "en", "product_line": "…", "persona": "…",
               "market": "…", "priority": 1, "rationale": "…"}]
  }
  ```
  入库规则：全部以 `review_status=pending` 落库；`seeds` 须先经 `seed.query` 唯一性过滤（FR-010）。
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

- 每类适配器实现向 **Provider Registry** 注册：`{type_key, display_name, config_schema(JSON Schema), secret_fields[], factory}`。
- 前端通过 `GET /api/v1/<类别>/providers` 读取 `config_schema` 动态渲染配置表单（这样新增提供方无需改前端）。
- `POST /…/{id}/test` 统一映射到适配器的 `test_connection()/verify()`。

## 6. 新增提供方的检查单

1. 实现对应 Protocol；2. 注册 manifest（type_key、config_schema、secret_fields）；3. 提供 fixture 级联调（不依赖真实凭证的假实现）；4. 明确错误分类映射；5. 在 research.md"后续可接入"清单中登记候选。
