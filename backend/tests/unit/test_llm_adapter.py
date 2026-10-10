"""LLM 适配器测试：解析卫生 / schema 修复循环 / 错误分类（桩客户端，离线）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.llm.openai_compatible import OpenAICompatibleProvider, extract_json_block

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "string"}}},
    "required": ["items"],
}


def _response(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class StubClient:
    """最小聊天桩：按脚本依次返回内容。"""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                return _response(outer.responses.pop(0))

        self.chat = SimpleNamespace(completions=_Completions())


def _provider(responses: list[str]) -> tuple[OpenAICompatibleProvider, StubClient]:
    client = StubClient(responses)
    provider = OpenAICompatibleProvider(
        base_url="http://stub", api_key="k", model="m", client_factory=lambda _t: client
    )
    return provider, client


def test_extract_json_block_variants():
    assert extract_json_block('{"a": 1}') == {"a": 1}
    assert extract_json_block('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_block('前置说明 {"a": 1} 尾注') == {"a": 1}
    assert extract_json_block('[{"x": 1}]') == [{"x": 1}]
    with pytest.raises(ProviderError) as excinfo:
        extract_json_block("完全没有 JSON")
    assert excinfo.value.kind == ErrorKind.INVALID_OUTPUT


def test_generate_structured_repairs_invalid_json():
    provider, client = _provider(["这不是 JSON", '{"items": ["ok"]}'])
    result = provider.generate_structured(prompt="p", schema=SCHEMA)
    assert result == {"items": ["ok"]}
    assert len(client.calls) == 2  # 第二次为修复重试
    # 修复重试消息里包含校验/格式提示
    assert any("严格 JSON" in m["content"] for m in client.calls[1]["messages"])


def test_generate_structured_repairs_schema_mismatch():
    provider, client = _provider(['{"items": 123}', '{"items": ["ok"]}'])
    result = provider.generate_structured(prompt="p", schema=SCHEMA)
    assert result == {"items": ["ok"]}
    assert len(client.calls) == 2


def test_generate_structured_gives_up_with_invalid_output():
    provider, client = _provider(["bad", "bad", "bad"])
    with pytest.raises(ProviderError) as excinfo:
        provider.generate_structured(prompt="p", schema=SCHEMA, max_repair_attempts=2)
    assert excinfo.value.kind == ErrorKind.INVALID_OUTPUT
    assert len(client.calls) == 3


def test_translate_ok_and_glossary_passed():
    provider, client = _provider(['{"items": ["A", "B"]}'])
    out = provider.translate(items=["甲", "乙"], source_lang="zh", target_lang="en", glossary={"螺栓": "bolt"})
    assert out == ["A", "B"]
    assert "螺栓 => bolt" in client.calls[0]["messages"][1]["content"]


def test_translate_count_mismatch_raises():
    provider, _client = _provider(['{"items": ["only-one"]}'])
    with pytest.raises(ProviderError) as excinfo:
        provider.translate(items=["甲", "乙"], source_lang="zh", target_lang="en")
    assert excinfo.value.kind == ErrorKind.INVALID_OUTPUT


def test_json_schema_capability_flag_selects_response_format():
    client = StubClient(['{"items": ["x"]}'])
    provider = OpenAICompatibleProvider(
        base_url="http://stub", api_key="k", model="m",
        supports_json_schema=True, client_factory=lambda _t: client,
    )
    provider.generate_structured(prompt="p", schema=SCHEMA)
    assert client.calls[0]["response_format"]["type"] == "json_schema"

    client2 = StubClient(['{"items": ["x"]}'])
    provider2 = OpenAICompatibleProvider(
        base_url="http://stub", api_key="k", model="m",
        supports_json_schema=False, client_factory=lambda _t: client2,
    )
    provider2.generate_structured(prompt="p", schema=SCHEMA)
    assert client2.calls[0]["response_format"]["type"] == "json_object"
