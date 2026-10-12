"""T206 契约测试：Mojeek 网页解析渠道（results-standard 解析 / 403 识别 / 合法空）。

样本为合成 fixture（形状参照 research R6 与社区选择器：ul.results-standard、a.title、a.ob、p.s；
403 由状态码或页面标题标记承载）。
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from saler.providers.errors import ErrorKind, ProviderError

MOJEEK_URL = "https://www.mojeek.com/search"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "search_pages" / "mojeek"

BLANK_HTML = "<html><body><p>blank</p></body></html>"


def fx(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _engine():
    from saler.providers.search.mojeek import MojeekHTMLEngine

    return MojeekHTMLEngine(params={"interval_s": 0})


class TestMojeekParse:
    @respx.mock
    def test_results_standard_parsed(self):
        respx.get(MOJEEK_URL).mock(return_value=httpx.Response(200, text=fx("results.html")))
        items = _engine().search(query="test")
        assert [i.title for i in items] == ["独立索引结果一", "独立索引结果二"]
        assert items[0].url == "https://independent.example/one"
        assert items[0].snippet == "独立索引摘要一"

    @respx.mock
    def test_no_results_page_is_legal_empty(self):
        respx.get(MOJEEK_URL).mock(return_value=httpx.Response(200, text=fx("no_results.html")))
        assert _engine().search(query="test") == []

    @respx.mock
    def test_container_missing_is_blocked(self):
        respx.get(MOJEEK_URL).mock(return_value=httpx.Response(200, text=BLANK_HTML))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="test")
        assert ei.value.kind == ErrorKind.BLOCKED


class TestMojeekBlocked:
    @respx.mock
    def test_http_403_is_blocked(self):
        respx.get(MOJEEK_URL).mock(return_value=httpx.Response(403, text=fx("forbidden.html")))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="test")
        assert ei.value.kind == ErrorKind.BLOCKED

    @respx.mock
    def test_forbidden_title_marker_200_is_blocked(self):
        # 200 但页面标题为 403 - Forbidden（社区实证形态）
        respx.get(MOJEEK_URL).mock(return_value=httpx.Response(200, text=fx("forbidden.html")))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="test")
        assert ei.value.kind == ErrorKind.BLOCKED


class TestMojeekManifest:
    def test_registered_with_preset(self):
        import saler.providers.search  # noqa: F401
        from saler.providers.registry import registry

        m = registry.get("search", "mojeek_html")
        assert m is not None and m.preset is not None
        assert m.secret_fields == ()
        assert m.preset["access_mode"] == "html"
        assert m.preset["apply_url"] is None
