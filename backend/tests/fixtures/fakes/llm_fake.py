"""假 LLM Provider：脚本化输出，离线契约测试用。

支持 `on_attempt` 逐次尝试回调（与真实适配器同契约）：
`event="start"`（请求发出，结果未知）先于 `event="finish"`（本次尝试结束）；
任务层据此写入/收口 llm_call 明细。
"""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Callable
from typing import Any

from saler.providers.errors import ProviderError
from saler.providers.llm.base import TestResult


def default_expansion() -> dict:
    """一次合理的"知识图谱扩充"输出样例（种子为中文母版，机构名保留原文）。"""
    return {
        "nodes": [
            {
                "node_type": "org",
                "name": "Fake Utility Co",
                "attributes": {"org_type": "utility"},
                "confidence": 0.7,
                "rationale": "示例具名实体",
            },
            {"node_type": "persona", "name": "公用事业", "attributes": {}, "confidence": 0.9},
        ],
        "edges": [{"from": "Fake Utility Co", "to": "公用事业", "relation_type": "org_has_persona"}],
        "seeds": [
            {
                "query": '"Fake Utility Co" 联系方式',
                "persona": "公用事业",
                "priority": 1,
                "rationale": "具名实体精度高",
            },
            {
                "query": "电力金具 五金经销 肯尼亚",
                "product_line": "电力金具",
                "market": "肯尼亚",
                "priority": 2,
            },
        ],
    }


class FakeLLMProvider:
    type_key = "fake"
    provider_name = "fake"
    model = "fake-model"

    def __init__(self, script: list[Any] | None = None) -> None:
        self.script: deque[Any] = deque(script or [])
        self.calls: list[dict] = []
        self.available = True

    def _emit(
        self,
        on_attempt: Callable[[dict], None] | None,
        *,
        messages: list[dict],
        response_text: str | None,
        error: Exception | None = None,
        event: str = "finish",
    ) -> None:
        if on_attempt is None:
            return
        error_kind = (
            error.kind.value
            if isinstance(error, ProviderError)
            else (type(error).__name__ if error is not None else None)
        )
        started = event == "start"
        on_attempt(
            {
                "event": event,
                "provider": self.provider_name,
                "model": self.model,
                "attempt": 1,
                "messages": [dict(m) for m in messages],
                "response_text": None if started else response_text,
                "ok": None if started else error is None,
                "error_kind": None if started else error_kind,
                "error_detail": None if started else (str(error) if error is not None else None),
                "latency_ms": None if started else 1,
                "usage": None,
            }
        )

    def test_connection(self) -> TestResult:
        return TestResult(ok=self.available, detail="fake ok", models=["fake-model"])

    def generate_structured(
        self,
        *,
        prompt: str,
        schema: dict,
        system: str | None = None,
        max_repair_attempts: int = 2,
        timeout_s: float = 120,
        deadline_s: float = 300,
        on_attempt: Callable[[dict], None] | None = None,
    ) -> dict:
        self.calls.append({"prompt": prompt, "schema": schema})
        item = self.script.popleft() if self.script else default_expansion()
        messages = [{"role": "user", "content": prompt}]
        self._emit(on_attempt, messages=messages, response_text=None, event="start")
        if isinstance(item, Exception):
            self._emit(on_attempt, messages=messages, response_text=None, error=item)
            raise item
        self._emit(
            on_attempt,
            messages=messages,
            response_text=json.dumps(item, ensure_ascii=False),
        )
        return item

    def translate(
        self,
        *,
        items: list[str],
        source_lang: str,
        target_lang: str,
        glossary: dict[str, str] | None = None,
        timeout_s: float = 120,
        deadline_s: float = 300,
        on_attempt: Callable[[dict], None] | None = None,
    ) -> list[str]:
        self.calls.append({"translate": list(items), "target": target_lang, "glossary": glossary})
        out = [f"[{target_lang}] {item}" for item in items]
        messages = [{"role": "user", "content": "\n".join(items)}]
        self._emit(on_attempt, messages=messages, response_text=None, event="start")
        self._emit(
            on_attempt,
            messages=messages,
            response_text=json.dumps({"items": out}, ensure_ascii=False),
        )
        return out

    def complete(self, *, prompt: str, system: str | None = None, timeout_s: float = 120) -> str:
        return "fake-complete"
