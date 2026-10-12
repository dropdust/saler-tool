"""T207 契约测试：Wikipedia 官方面向免密钥 API（条目粒度 / 语言版本 / 描述性 UA / 429）。

样本为合成 fixture（形状参照 research R7 与 MediaWiki Action API：action=query&list=search，
formatversion=2 的 query.search[]：title/snippet(HTML)/pageid）。
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from saler.providers.errors import ErrorKind, ProviderError

EN_API = "https://en.wikipedia.org/w/api.php"
ZH_API = "https://zh.wikipedia.org/w/api.php"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "search_pages" / "wikipedia"


def fx_json() -> dict:
    return json.loads((FIXTURES / "search.json").read_text(encoding="utf-8"))


def _engine(**params):
    from saler.providers.search.wikipedia import WikipediaEngine

    return WikipediaEngine(params={"interval_s": 0, **params})


class TestWikipediaSearch:
    @respx.mock
    def test_params_and_parse_with_snippet_cleaned(self):
        route = respx.get(EN_API).mock(return_value=httpx.Response(200, json=fx_json()))
        items = _engine().search(query="Rust 语言", count=5)
        req = route.calls[0].request
        assert req.url.params["action"] == "query"
        assert req.url.params["list"] == "search"
        assert req.url.params["srsearch"] == "Rust 语言"
        assert req.url.params["srlimit"] == "5"
        assert req.url.params["srprop"] == "snippet"
        assert req.url.params["formatversion"] == "2"
        assert items[0].title == "Rust (programming language)"
        assert items[0].url == "https://en.wikipedia.org/wiki/Rust_(programming_language)"
        assert items[0].snippet == "Rust 是一门系统编程语言"  # HTML 标签已清洗
        assert items[1].url == "https://en.wikipedia.org/wiki/Rust"

    @respx.mock
    def test_descriptive_ua(self):
        route = respx.get(EN_API).mock(return_value=httpx.Response(200, json=fx_json()))
        _engine(contact="ops@example.com").search(query="q")
        ua = route.calls[0].request.headers["User-Agent"]
        assert ua.startswith("SalerTool/")  # Wikimedia 政策：描述性 UA
        assert "ops@example.com" in ua

    @respx.mock
    def test_lang_param_switches_subdomain_and_call_arg_overrides(self):
        zh_route = respx.get(ZH_API).mock(return_value=httpx.Response(200, json=fx_json()))
        eng = _engine(lang="zh")
        eng.search(query="q")
        assert zh_route.called  # 渠道配置默认语言
        zh_route.reset()
        _engine(lang="en").search(query="q", lang="zh")
        assert zh_route.called  # 调用方 lang 覆盖

    @respx.mock
    def test_srlimit_clamped_to_50(self):
        route = respx.get(EN_API).mock(return_value=httpx.Response(200, json=fx_json()))
        _engine().search(query="q", count=200)
        assert route.calls[0].request.url.params["srlimit"] == "50"


class TestWikipediaErrors:
    @respx.mock
    def test_empty_search_is_legal_empty(self):
        respx.get(EN_API).mock(return_value=httpx.Response(200, json={"batchcomplete": True}))
        assert _engine().search(query="q") == []
        respx.get(EN_API).mock(return_value=httpx.Response(200, json={"query": {"search": []}}))
        assert _engine().search(query="q") == []

    @respx.mock
    def test_429_is_rate_limit(self):
        respx.get(EN_API).mock(return_value=httpx.Response(429, headers={"Retry-After": "5"}))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="q")
        assert ei.value.kind == ErrorKind.RATE_LIMIT

    @respx.mock
    def test_non_json_response_is_server(self):
        respx.get(EN_API).mock(return_value=httpx.Response(200, text="<html>oops</html>"))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="q")
        assert ei.value.kind == ErrorKind.SERVER


class TestWikipediaManifest:
    def test_registered_as_official_api_without_key(self):
        import saler.providers.search  # noqa: F401
        from saler.providers.registry import registry

        m = registry.get("search", "wikipedia")
        assert m is not None and m.preset is not None
        assert m.secret_fields == ()
        assert m.preset["access_mode"] == "official_api"
        assert m.preset["apply_url"] is None
        assert "佐证" in m.preset["market"] or "佐证" in m.preset["risk"]
