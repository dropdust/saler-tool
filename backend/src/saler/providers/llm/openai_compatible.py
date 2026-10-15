"""OpenAI 兼容 LLM 适配器（覆盖 DeepSeek / Qwen-DashScope / Moonshot-Kimi / OpenAI / Ollama）。

工程约定（research.md §6）：
- 输出永不信任服务商：一律应用侧 jsonschema 校验 + 有限修复重试（≤3 次尝试）；
- 按能力标记选择请求策略：``supports_json_schema`` 为真用 json_schema，否则 json_object + 强提示；
- 连接测试优先 ``GET /models``，失败回退 1-token ping，原样呈现服务商错误文本；
- 调用有硬时限（T271）：单次模型调用（含解析/修复重试全程）超 `DEFAULT_CALL_DEADLINE_S` 即中断，
  不跟随服务端/中间层挂起（同步阻塞调用无法从外部取消 → 放弃等待 + 主动断连）；
- 不做隐藏重试（``max_retries=0``）：一次尝试 = 一次请求，重试编排归任务层（contracts/provider-adapters.md）。
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
from typing import Any

import jsonschema
from loguru import logger

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.llm.base import TestResult
from saler.providers.llm.schemas import TRANSLATION_LIST_SCHEMA
from saler.providers.registry import ProviderManifest, registry

#: 单次模型调用（generate_structured / translate 的一次调用）的墙钟上限（秒）
DEFAULT_CALL_DEADLINE_S = 300.0
#: 连接超时与读超时分开：连不上要快速失败，读大响应可放宽
CONNECT_TIMEOUT_S = 10.0

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
    raise ProviderError(ErrorKind.INVALID_OUTPUT, "模型输出不是有效 JSON", detail=(text or "")[:500])


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


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _close_quietly(client: Any) -> None:
    """尽力关闭客户端（断连、释放连接池）；替身/桩客户端没有 close 时静默跳过。"""
    close = getattr(client, "close", None)
    if close is None:
        return
    try:
        close()
    except Exception:  # noqa: BLE001 - 关闭失败不影响调用结论
        logger.debug("关闭 LLM 客户端失败（忽略）")


def run_with_deadline(fn: Callable[[], Any], *, seconds: float, on_timeout: Callable[[], None] | None = None) -> Any:
    """在守护线程执行 ``fn``，超过 ``seconds`` 秒未返回即放弃：先尽力 ``on_timeout()``（如断连），再抛 TimeoutError。

    - 同步阻塞的 HTTP 调用无法从外部取消，故以"放弃等待 + 主动断连"实现墙钟硬上限；
    - 被放弃线程的返回值/异常一律丢弃：迟到结果不得二次上报（llm_call 明细不出现幽灵行）。
    """
    if seconds <= 0:
        raise TimeoutError("调用时限已耗尽")
    box: dict[str, Any] = {}
    finished = threading.Event()

    def _run() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - 原样转交调用线程
            box["error"] = exc
        finally:
            finished.set()

    worker = threading.Thread(target=_run, name="llm-call", daemon=True)
    worker.start()
    if not finished.wait(seconds):
        if on_timeout is not None:
            try:
                on_timeout()
            except Exception:  # noqa: BLE001 - 断连失败不改变"已超时"结论
                logger.debug("超时后断连失败（忽略）")
        raise TimeoutError(f"模型响应超过 {seconds:.0f}s 未返回")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _usage_to_dict(usage: Any) -> dict | None:
    """openai SDK usage（pydantic 模型）→ dict（供明细落库）；未知形态返回 None。"""
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return dict(usage)
    return None


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
        #: 最近一次 _chat 的 token 用量（openai SDK usage 的 dict 形式，可能为 None）
        self._last_usage: dict | None = None
        self._api_key = api_key
        self._client_factory = client_factory or self._default_client_factory

    # ---- 传输 ----
    def _default_client_factory(self, timeout_s: float) -> Any:
        import httpx
        from openai import OpenAI

        return OpenAI(
            base_url=self.base_url,
            api_key=self._api_key,
            # 单次请求的 I/O 超时（连接单独收紧）；调用全程的墙钟上限在 _chat 的 run_with_deadline
            timeout=httpx.Timeout(timeout_s, connect=min(CONNECT_TIMEOUT_S, timeout_s)),
            max_retries=0,
        )

    def _extract_content(self, resp: Any) -> str:
        """取首条回复内容；响应体缺 choices / 结构异常一律显式报 server，绝不外泄 TypeError。"""
        choices = getattr(resp, "choices", None)
        if not choices:
            raise ProviderError(
                ErrorKind.SERVER,
                "服务商响应缺少 choices（网关截断或超时返回空壳）",
                provider=self.provider_name,
                detail=repr(resp)[:500],
            )
        content = getattr(getattr(choices[0], "message", None), "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, (list, dict)):  # 多段 content（多模态）→ 原样 JSON 化，交由解析卫生处理
            return json.dumps(content, ensure_ascii=False)
        return ""

    def _chat(
        self,
        *,
        messages: list[dict[str, str]],
        response_format: dict | None = None,
        timeout_s: float = 120,
        deadline_s: float | None = None,
    ) -> str:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if response_format is not None:
            kwargs["response_format"] = response_format
        budget = timeout_s if deadline_s is None else deadline_s
        client = self._client_factory(timeout_s)
        try:
            try:
                resp = run_with_deadline(
                    lambda: client.chat.completions.create(**kwargs),
                    seconds=budget,
                    on_timeout=lambda: _close_quietly(client),
                )
            except TimeoutError as exc:
                raise ProviderError(
                    ErrorKind.TIMEOUT,
                    f"模型调用超过 {budget:.0f}s 未返回（已中断连接）",
                    provider=self.provider_name,
                    detail=str(exc),
                ) from exc
            except ProviderError:
                raise
            except Exception as exc:
                raise map_openai_error(exc, provider=self.provider_name) from exc
        finally:
            _close_quietly(client)
        # 仅在真正拿到响应后才记录用量（超时被放弃的线程不得迟到改写）
        self._last_usage = _usage_to_dict(getattr(resp, "usage", None))
        return self._extract_content(resp)

    def _emit_attempt(
        self,
        on_attempt: Callable[[dict], None] | None,
        *,
        event: str,
        attempt: int,
        messages: list[dict[str, str]],
        response_text: str | None,
        ok: bool | None,
        error_kind: str | None,
        error_detail: str | None,
        latency_ms: int | None,
        usage: dict | None,
    ) -> None:
        """把一次尝试的输入/输出交给记录方（llm_call 明细）；观测失败不影响调用。

        - ``event="start"``：请求即将发出（ok/latency/输出一律为空；卡住时据此判断已发到哪一步）；
        - ``event="finish"``：本次尝试结束（成功或失败）。
        """
        if on_attempt is None:
            return
        payload = {
            "event": event,
            "provider": self.provider_name,
            "model": self.model,
            "attempt": attempt,
            "messages": [dict(m) for m in messages],
            "response_text": response_text,
            "ok": ok,
            "error_kind": error_kind,
            "error_detail": error_detail,
            "latency_ms": latency_ms,
            "usage": usage,
        }
        try:
            on_attempt(payload)
        except Exception:  # noqa: BLE001 - 观测失败不得中断模型调用
            logger.warning("LLM 调用明细记录失败（忽略，不影响本次调用）")

    # ---- 契约方法 ----
    def test_connection(self) -> TestResult:
        try:
            client = self._client_factory(15)
            try:  # 同 _chat：探测也有硬时限，挂起的服务端不会把"测试连接"吊住
                models = run_with_deadline(
                    lambda: client.models.list(),
                    seconds=15,
                    on_timeout=lambda: _close_quietly(client),
                )
            finally:
                _close_quietly(client)
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
        deadline_s: float = DEFAULT_CALL_DEADLINE_S,
        on_attempt: Callable[[dict], None] | None = None,
    ) -> dict:
        sys_text = system or (
            "你只输出严格 JSON（json 对象），不要 Markdown 围栏、不要额外解释。"
            '输出必须满足调用方给出的 JSON Schema。示例：{"..."}。'
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": prompt},
        ]
        last_error: str = ""
        deadline = time.monotonic() + deadline_s
        self.last_stats = {"attempts": 0, "repair_attempts": 0, "ok": False, "error_kind": None}
        for _attempt in range(max_repair_attempts + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:  # 全程时限已到：不再发请求（修复重试同样受限于此）
                self.last_stats["error_kind"] = ErrorKind.TIMEOUT.value
                raise ProviderError(
                    ErrorKind.TIMEOUT,
                    f"模型调用总时长超过 {deadline_s:.0f}s（含解析与修复重试全程）",
                    provider=self.provider_name,
                    detail=last_error[:500],
                )
            attempt_no = _attempt + 1
            self.last_stats["attempts"] = attempt_no
            self.last_stats["repair_attempts"] = _attempt
            self._last_usage = None
            self._emit_attempt(
                on_attempt,
                event="start",
                attempt=attempt_no,
                messages=messages,
                response_text=None,
                ok=None,
                error_kind=None,
                error_detail=None,
                latency_ms=None,
                usage=None,
            )
            started = time.perf_counter()
            try:
                text = self._chat(
                    messages=messages,
                    response_format=self._response_format(schema),
                    timeout_s=timeout_s,
                    deadline_s=max(deadline - time.monotonic(), 0.0),
                )
            except ProviderError as exc:
                self._emit_attempt(
                    on_attempt,
                    event="finish",
                    attempt=attempt_no,
                    messages=messages,
                    response_text=None,
                    ok=False,
                    error_kind=exc.kind.value,
                    error_detail=str(exc),
                    latency_ms=_elapsed_ms(started),
                    usage=None,
                )
                raise
            latency_ms = _elapsed_ms(started)
            usage = self._last_usage
            try:
                data = extract_json_block(text)
            except ProviderError as exc:
                last_error = f"非 JSON：{exc}"
                self._emit_attempt(
                    on_attempt,
                    event="finish",
                    attempt=attempt_no,
                    messages=messages,
                    response_text=text,
                    ok=False,
                    error_kind=ErrorKind.INVALID_OUTPUT.value,
                    error_detail=last_error,
                    latency_ms=latency_ms,
                    usage=usage,
                )
                messages.append({"role": "assistant", "content": text[:2000]})
                messages.append(
                    {"role": "user", "content": "请仅返回严格 JSON（无围栏、无解释），并满足给定 schema。"}
                )
                continue
            try:
                jsonschema.validate(data, schema)
            except jsonschema.ValidationError as exc:
                last_error = f"schema 校验失败：{exc.message}（路径：{list(exc.absolute_path)}）"
                self._emit_attempt(
                    on_attempt,
                    event="finish",
                    attempt=attempt_no,
                    messages=messages,
                    response_text=text,
                    ok=False,
                    error_kind=ErrorKind.INVALID_OUTPUT.value,
                    error_detail=last_error,
                    latency_ms=latency_ms,
                    usage=usage,
                )
                logger.debug(f"LLM 输出校验失败，发起修复：{last_error}")
                messages.append({"role": "assistant", "content": text[:2000]})
                messages.append(
                    {
                        "role": "user",
                        "content": f"你上一次的 JSON 未通过校验：{last_error}。请返回修正后的严格 JSON。",
                    }
                )
                continue
            self._emit_attempt(
                on_attempt,
                event="finish",
                attempt=attempt_no,
                messages=messages,
                response_text=text,
                ok=True,
                error_kind=None,
                error_detail=None,
                latency_ms=latency_ms,
                usage=usage,
            )
            self.last_stats["ok"] = True
            return data
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
        deadline_s: float = DEFAULT_CALL_DEADLINE_S,
        on_attempt: Callable[[dict], None] | None = None,
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
            prompt=prompt,
            schema=TRANSLATION_LIST_SCHEMA,
            timeout_s=timeout_s,
            deadline_s=deadline_s,
            on_attempt=on_attempt,
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
