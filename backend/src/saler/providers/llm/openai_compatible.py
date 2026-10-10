"""OpenAI 兼容 LLM 适配器（覆盖 DeepSeek / Qwen-DashScope / Moonshot-Kimi / OpenAI / Ollama）。

工程约定（research.md §6）：
- 输出永不信任服务商：一律应用侧 jsonschema 校验 + 有限修复重试（≤3 次尝试）；
- 按能力标记选择请求策略：``supports_json_schema`` 为真用 json_schema，否则 json_object + 强提示；
- 连接测试优先 ``GET /models``，失败回退 1-token ping，原样呈现服务商错误文本。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import jsonschema
from loguru import logger

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.llm.base import TestResult
from saler.providers.llm.schemas import TRANSLATION_LIST_SCHEMA
from saler.providers.registry import ProviderManifest, registry

# 首批预置（模型 ID 以 GET /models 实测为准，不硬编码；model 留空由用户填写）
PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "display": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "supports_json_schema": False,
    },
    "qwen": {
        "display": "通义千问（DashScope OpenAI 兼容）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "supports_json_schema": True,
    },
    "moonshot": {
        "display": "Moonshot / Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "supports_json_schema": True,
    },
    "openai": {
        "display": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "supports_json_schema": True,
    },
    "ollama": {
        "display": "Ollama（本地，结构化输出由本机引擎约束）",
        "base_url": "http://localhost:11434/v1",
        "supports_json_schema": True,
    },
}


def extract_json_block(text: str) -> Any:
    """解析卫生：去 Markdown 围栏 → 取最外层 {...}/[...] → json.loads。"""
    t = (text or "").strip()
    t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (t.find("{"), t.find("[")) if i != -1]
    if starts:
        start = min(starts)
        for end in range(len(t) - 1, start, -1):
            if t[end] in "}]":
                try:
                    return json.loads(t[start : end + 1])
                except json.JSONDecodeError:
                    continue
    raise ProviderError(
        ErrorKind.INVALID_OUTPUT, "模型输出不是有效 JSON", detail=(text or "")[:500]
    )


def map_openai_error(exc: Exception, *, provider: str) -> ProviderError:
    try:
        import openai

        if isinstance(exc, openai.AuthenticationError):
            return ProviderError(ErrorKind.AUTH, str(exc), provider=provider)
        if isinstance(exc, openai.PermissionDeniedError):
            return ProviderError(ErrorKind.AUTH, str(exc), provider=provider)
        if isinstance(exc, openai.RateLimitError):
            return ProviderError(ErrorKind.RATE_LIMIT, str(exc), provider=provider)
        if isinstance(exc, openai.APITimeoutError):
            return ProviderError(ErrorKind.TIMEOUT, str(exc), provider=provider)
        if isinstance(exc, openai.APIConnectionError):
            return ProviderError(ErrorKind.NETWORK, str(exc), provider=provider)
        if isinstance(exc, openai.APIStatusError):
            status = getattr(exc, "status_code", 500) or 500
            kind = ErrorKind.SERVER if status >= 500 else ErrorKind.AUTH
            return ProviderError(kind, str(exc), provider=provider)
    except ImportError:  # pragma: no cover
        pass
    if isinstance(exc, ProviderError):
        return exc
    return ProviderError(ErrorKind.NETWORK, f"{type(exc).__name__}: {exc}", provider=provider)


class OpenAICompatibleProvider:
    type_key = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        supports_json_schema: bool = False,
        temperature: float | None = None,
        provider_name: str = "openai_compatible",
        client_factory: Callable[[float], Any] | None = None,
    ) -> None:
        self.base_url = base_url
        self.model = model
        self.supports_json_schema = supports_json_schema
        self.temperature = temperature
        self.provider_name = provider_name
        #: 最近一次 generate_structured 的调用统计（供任务层遥测记录，T137）
        self.last_stats: dict | None = None
        self._api_key = api_key
        self._client_factory = client_factory or self._default_client_factory

    # ---- 传输 ----
    def _default_client_factory(self, timeout_s: float) -> Any:
        from openai import OpenAI

        return OpenAI(base_url=self.base_url, api_key=self._api_key, timeout=timeout_s)

    def _chat(
        self,
        *,
        messages: list[dict[str, str]],
        response_format: dict | None = None,
        timeout_s: float = 120,
    ) -> str:
        try:
            client = self._client_factory(timeout_s)
            kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
            if self.temperature is not None:
                kwargs["temperature"] = self.temperature
            if response_format is not None:
                kwargs["response_format"] = response_format
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except ProviderError:
            raise
        except Exception as exc:
            raise map_openai_error(exc, provider=self.provider_name) from exc

    # ---- 契约方法 ----
    def test_connection(self) -> TestResult:
        try:
            client = self._client_factory(15)
            models = client.models.list()
            names = [m.id for m in getattr(models, "data", [])][:50]
            return TestResult(ok=True, detail="连接成功（已获取模型列表）", models=names)
        except Exception as first:
            logger.debug(f"models.list 探测失败（{type(first).__name__}: {first}），回退轻量 ping")
            try:
                self._chat(messages=[{"role": "user", "content": "ping"}], timeout_s=15)
                return TestResult(ok=True, detail="连接成功（轻量探测）")
            except ProviderError as exc:
                return TestResult(ok=False, detail=f"[{exc.kind.value}] {exc}")

    def _response_format(self, schema: dict) -> dict:
        if self.supports_json_schema:
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.get("title", "output"),
                    "schema": schema,
                    "strict": False,
                },
            }
        return {"type": "json_object"}

    def generate_structured(
        self,
        *,
        prompt: str,
        schema: dict,
        system: str | None = None,
        max_repair_attempts: int = 2,
        timeout_s: float = 120,
    ) -> dict:
        sys_text = system or (
            "你只输出严格 JSON（json 对象），不要 Markdown 围栏、不要额外解释。"
            "输出必须满足调用方给出的 JSON Schema。示例：{\"...\"}。"
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": prompt},
        ]
        last_error: str = ""
        self.last_stats = {"attempts": 0, "repair_attempts": 0, "ok": False, "error_kind": None}
        for _attempt in range(max_repair_attempts + 1):
            self.last_stats["attempts"] = _attempt + 1
            self.last_stats["repair_attempts"] = _attempt
            text = self._chat(
                messages=messages, response_format=self._response_format(schema), timeout_s=timeout_s
            )
            try:
                data = extract_json_block(text)
            except ProviderError as exc:
                last_error = f"非 JSON：{exc}"
                messages.append({"role": "assistant", "content": text[:2000]})
                messages.append(
                    {"role": "user", "content": "请仅返回严格 JSON（无围栏、无解释），并满足给定 schema。"}
                )
                continue
            try:
                jsonschema.validate(data, schema)
                self.last_stats["ok"] = True
                return data
            except jsonschema.ValidationError as exc:
                last_error = f"schema 校验失败：{exc.message}（路径：{list(exc.absolute_path)}）"
                logger.debug(f"LLM 输出校验失败，发起修复：{last_error}")
                messages.append({"role": "assistant", "content": text[:2000]})
                messages.append(
                    {
                        "role": "user",
                        "content": f"你上一次的 JSON 未通过校验：{last_error}。请返回修正后的严格 JSON。",
                    }
                )
        self.last_stats["error_kind"] = ErrorKind.INVALID_OUTPUT.value
        raise ProviderError(
            ErrorKind.INVALID_OUTPUT,
            f"模型输出在 {max_repair_attempts + 1} 次尝试后仍未通过 schema 校验",
            provider=self.provider_name,
            detail=last_error[:500],
        )

    def translate(
        self,
        *,
        items: list[str],
        source_lang: str,
        target_lang: str,
        glossary: dict[str, str] | None = None,
        timeout_s: float = 120,
    ) -> list[str]:
        if not items:
            return []
        glossary_txt = ""
        if glossary:
            pairs = "\n".join(f"- {k} => {v}" for k, v in list(glossary.items())[:100])
            glossary_txt = f"\n术语表（必须采用指定译法）：\n{pairs}"
        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(items))
        prompt = (
            f"将以下 {source_lang} 文本逐条翻译为 {target_lang}。"
            f'仅输出 JSON：{{"items": ["译1", "译2", ...]}}，条数必须与输入一致（共 {len(items)} 条），'
            f"不得合并、增删或解释。{glossary_txt}\n\n输入：\n{numbered}"
        )
        data = self.generate_structured(
            prompt=prompt, schema=TRANSLATION_LIST_SCHEMA, timeout_s=timeout_s
        )
        out = list(data.get("items", []))
        if len(out) != len(items):
            raise ProviderError(
                ErrorKind.INVALID_OUTPUT,
                f"翻译条数与输入不一致（{len(out)} != {len(items)}）",
                provider=self.provider_name,
            )
        return [str(x) for x in out]

    def complete(self, *, prompt: str, system: str | None = None, timeout_s: float = 120) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._chat(messages=messages, timeout_s=timeout_s)


LLM_MANIFEST = ProviderManifest(
    kind="llm",
    type_key="openai_compatible",
    display_name="OpenAI 兼容（DeepSeek / Qwen / Kimi / OpenAI / Ollama）",
    config_schema={
        "type": "object",
        "properties": {
            "base_url": {"type": "string", "title": "接入地址", "examples": ["https://api.deepseek.com"]},
            "api_key": {"type": "string", "title": "API 密钥", "format": "password"},
            "model": {"type": "string", "title": "模型"},
            "supports_json_schema": {"type": "boolean", "title": "服务端严格 JSON Schema", "default": False},
            "temperature": {"type": "number", "title": "温度", "default": 0.3},
        },
        "required": ["base_url", "api_key", "model"],
    },
    secret_fields=("api_key",),
    factory=OpenAICompatibleProvider,
)
registry.register(LLM_MANIFEST)
