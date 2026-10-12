"""T049 契约测试：检索适配器（respx 离线）——解析/错误分类/故障转移/DDG 软封禁。"""

from __future__ import annotations

import httpx
import pytest
import respx

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.llm.base import TestResult

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
SERPER_URL = "https://google.serper.dev/search"
TAVILY_URL = "https://api.tavily.com/search"
DDG_URL = "https://html.duckduckgo.com/html/"
DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"


class TestBrave:
    @respx.mock
    def test_parses_results_and_sends_key(self):
        from saler.providers.search.brave import BraveSearchProvider

        route = respx.get(BRAVE_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "web": {
                        "results": [
                            {"title": "Acme Kenya", "url": "https://acme.co.ke", "description": "switchgear"}
                        ]
                    }
                },
            )
        )
        items = BraveSearchProvider(api_key="k-1").search(query="q", count=5)
        assert items[0].url == "https://acme.co.ke"
        assert items[0].snippet == "switchgear"
        assert route.calls[0].request.headers["X-Subscription-Token"] == "k-1"

    @respx.mock
    def test_rate_limit_maps_kind(self):
        from saler.providers.search.brave import BraveSearchProvider

        respx.get(BRAVE_URL).mock(return_value=httpx.Response(429, json={}))
        with pytest.raises(ProviderError) as excinfo:
            BraveSearchProvider(api_key="k").search(query="q")
        assert excinfo.value.kind == ErrorKind.RATE_LIMIT

    @respx.mock
    def test_auth_maps_kind(self):
        from saler.providers.search.brave import BraveSearchProvider

        respx.get(BRAVE_URL).mock(return_value=httpx.Response(401, json={}))
        with pytest.raises(ProviderError) as excinfo:
            BraveSearchProvider(api_key="bad").search(query="q")
        assert excinfo.value.kind == ErrorKind.AUTH


class TestSerper:
    @respx.mock
    def test_parses_results_and_sends_key(self):
        from saler.providers.search.serper import SerperSearchProvider

        route = respx.post(SERPER_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "organic": [
                        {"title": "Beta", "link": "https://beta.com", "snippet": "epc contractor"}
                    ]
                },
            )
        )
        items = SerperSearchProvider(api_key="s-1").search(query="q", count=10)
        assert items[0].url == "https://beta.com"
        request = route.calls[0].request
        assert request.headers["X-API-KEY"] == "s-1"
        assert b'"q"' in request.content

    @respx.mock
    def test_rate_limit_maps_kind(self):
        from saler.providers.search.serper import SerperSearchProvider

        respx.post(SERPER_URL).mock(return_value=httpx.Response(429, json={}))
        with pytest.raises(ProviderError) as excinfo:
            SerperSearchProvider(api_key="k").search(query="q")
        assert excinfo.value.kind == ErrorKind.RATE_LIMIT


class TestTavily:
    @respx.mock
    def test_parses_results(self):
        from saler.providers.search.tavily import TavilySearchProvider

        respx.post(TAVILY_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"title": "Gamma", "url": "https://gamma.io", "content": "utility"}
                    ]
                },
            )
        )
        items = TavilySearchProvider(api_key="t-1").search(query="q")
        assert items[0].url == "https://gamma.io"
        assert items[0].snippet == "utility"

    @respx.mock
    def test_server_error_maps_kind(self):
        from saler.providers.search.tavily import TavilySearchProvider

        respx.post(TAVILY_URL).mock(return_value=httpx.Response(503, json={}))
        with pytest.raises(ProviderError) as excinfo:
            TavilySearchProvider(api_key="k").search(query="q")
        assert excinfo.value.kind == ErrorKind.SERVER


class TestDdgFallback:
    NORMAL_HTML = """
    <html><body>
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Facme.co.ke%2Fcontact&rut=x">Acme</a>
      <a class="result__a" href="https://plain.example.org/page">Plain</a>
    </body></html>
    """
    ANOMALY_HTML = "<html><body><div class='anomaly-modal'>detected unusual traffic</div></body></html>"
    LITE_HTML = """
    <html><body>
      <a class="result-link" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Flite.example%2Fpage&rut=y">Lite Result</a>
    </body></html>
    """
    NO_RESULTS_HTML = "<html><body><div class='no-results'>No results.</div></body></html>"
    DETECT_PAGE_HTML = "<html><body>Please enable JavaScript to continue.</body></html>"

    @respx.mock
    def test_parses_and_decodes_redirect_urls(self):
        from saler.providers.search.ddg_fallback import DuckDuckGoFallbackProvider

        respx.get(DDG_URL).mock(return_value=httpx.Response(200, text=self.NORMAL_HTML))
        items = DuckDuckGoFallbackProvider().search(query="q")
        assert {item.url for item in items} == {"https://acme.co.ke/contact", "https://plain.example.org/page"}

    @respx.mock
    def test_soft_block_202_is_failure(self):
        from saler.providers.search.ddg_fallback import DuckDuckGoFallbackProvider

        respx.get(DDG_URL).mock(return_value=httpx.Response(202, text=self.ANOMALY_HTML))
        with pytest.raises(ProviderError) as excinfo:
            DuckDuckGoFallbackProvider(params={"interval_s": 0}).search(query="q")
        assert excinfo.value.kind == ErrorKind.BLOCKED

    @respx.mock
    def test_anomaly_page_200_is_failure(self):
        from saler.providers.search.ddg_fallback import DuckDuckGoFallbackProvider

        respx.get(DDG_URL).mock(return_value=httpx.Response(200, text=self.ANOMALY_HTML))
        with pytest.raises(ProviderError) as excinfo:
            DuckDuckGoFallbackProvider(params={"interval_s": 0}).search(query="q")
        assert excinfo.value.kind == ErrorKind.BLOCKED

    @respx.mock
    def test_lite_fallback_when_html_soft_blocked(self):
        from saler.providers.search.ddg_fallback import DuckDuckGoFallbackProvider

        respx.get(DDG_URL).mock(return_value=httpx.Response(202, text=""))
        lite = respx.get(DDG_LITE_URL).mock(return_value=httpx.Response(200, text=self.LITE_HTML))
        items = DuckDuckGoFallbackProvider(params={"interval_s": 0}).search(query="q")
        assert lite.called  # html 软封禁 → lite 形态回退一次
        assert items[0].url == "https://lite.example/page"

    @respx.mock
    def test_legal_empty_with_marker(self):
        from saler.providers.search.ddg_fallback import DuckDuckGoFallbackProvider

        respx.get(DDG_URL).mock(return_value=httpx.Response(200, text=self.NO_RESULTS_HTML))
        assert DuckDuckGoFallbackProvider(params={"interval_s": 0}).search(query="q") == []

    @respx.mock
    def test_detection_page_without_marker_is_blocked(self):
        from saler.providers.search.ddg_fallback import DuckDuckGoFallbackProvider

        respx.get(DDG_URL).mock(return_value=httpx.Response(200, text=self.DETECT_PAGE_HTML))
        respx.get(DDG_LITE_URL).mock(return_value=httpx.Response(403))
        with pytest.raises(ProviderError) as excinfo:
            DuckDuckGoFallbackProvider(params={"interval_s": 0}).search(query="q")
        assert excinfo.value.kind == ErrorKind.BLOCKED

    @respx.mock
    def test_browser_ua_and_referer_sent(self):
        from saler.providers.search.ddg_fallback import DuckDuckGoFallbackProvider

        route = respx.get(DDG_URL).mock(return_value=httpx.Response(200, text=self.NORMAL_HTML))
        DuckDuckGoFallbackProvider(params={"interval_s": 0}).search(query="q")
        req = route.calls[0].request
        assert "Mozilla" in req.headers["User-Agent"]
        assert req.headers["Referer"] == "https://duckduckgo.com/"

    def test_manifest_preset(self):
        import saler.providers.search  # noqa: F401
        from saler.providers.registry import registry

        m = registry.get("search", "ddg_html")
        assert m is not None and m.preset is not None
        assert m.preset["access_mode"] == "html"
        assert m.preset["apply_url"] is None
        assert m.secret_fields == ()


class _StubProvider:
    type_key = "stub"

    def __init__(self, name: str, *, error: Exception | None = None, results: list | None = None):
        self.name = name
        self.error = error
        self.results = results or []
        self.calls = 0

    def search(self, *, query: str, count: int = 20, lang=None, country=None, timeout_s=30):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.results

    def test_connection(self):
        return TestResult(ok=True)


class TestFailover:
    def test_switches_to_next_on_rate_limit(self):
        from saler.providers.search.base import SearchItem
        from saler.providers.search.failover import SearchFailover

        first = _StubProvider("first", error=ProviderError(ErrorKind.RATE_LIMIT, "429"))
        second = _StubProvider("second", results=[SearchItem(title="t", url="https://ok.com", snippet="")])
        receiver = SearchFailover([first, second]).search(query="q")
        assert [item.url for item in receiver] == ["https://ok.com"]
        assert first.calls == 1 and second.calls == 1

    def test_all_fail_raises_last_error(self):
        from saler.providers.search.failover import SearchFailover

        first = _StubProvider("first", error=ProviderError(ErrorKind.RATE_LIMIT, "429"))
        second = _StubProvider("second", error=ProviderError(ErrorKind.BLOCKED, "ddg"))
        with pytest.raises(ProviderError) as excinfo:
            SearchFailover([first, second]).search(query="q")
        assert excinfo.value.kind == ErrorKind.BLOCKED

    def test_empty_chain_is_misconfiguration(self):
        from saler.providers.search.failover import SearchFailover

        with pytest.raises(ProviderError) as excinfo:
            SearchFailover([]).search(query="q")
        assert excinfo.value.kind == ErrorKind.AUTH
