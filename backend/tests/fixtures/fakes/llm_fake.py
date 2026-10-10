"""假 LLM Provider：脚本化输出，离线契约测试用。"""

from __future__ import annotations

from collections import deque
from typing import Any

from saler.providers.llm.base import TestResult


def default_expansion() -> dict:
    """一次合理的"知识图谱扩充"输出样例。"""
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
        "edges": [
            {"from": "Fake Utility Co", "to": "公用事业", "relation_type": "org_has_persona"}
        ],
        "seeds": [
            {
                "query": '"Fake Utility Co" contact',
                "lang": "en",
                "persona": "公用事业",
                "priority": 1,
                "rationale": "具名实体精度高",
            },
            {"query": "power line hardware distributor kenya", "lang": "en", "priority": 2},
        ],
    }


class FakeLLMProvider:
    type_key = "fake"

    def __init__(self, script: list[Any] | None = None) -> None:
        self.script: deque[Any] = deque(script or [])
        self.calls: list[dict] = []
        self.available = True

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
    ) -> dict:
        self.calls.append({"prompt": prompt, "schema": schema})
        item = self.script.popleft() if self.script else default_expansion()
        if isinstance(item, Exception):
            raise item
        return item

    def translate(
        self,
        *,
        items: list[str],
        source_lang: str,
        target_lang: str,
        glossary: dict[str, str] | None = None,
        timeout_s: float = 120,
    ) -> list[str]:
        self.calls.append({"translate": list(items), "target": target_lang, "glossary": glossary})
        return [f"[{target_lang}] {item}" for item in items]

    def complete(self, *, prompt: str, system: str | None = None, timeout_s: float = 120) -> str:
        return "fake-complete"
