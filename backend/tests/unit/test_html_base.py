"""T203 单元测试：HTML 渠道共基类（节流 / UA 池 / 安全失败编排 / 会话持久化）。

纪律来源：contract §4.1/§4.2（风控识别、空结果三分支）、research R10/R12。
"""

from __future__ import annotations

import httpx
import pytest
import respx
from selectolax.lexbor import LexborHTMLParser

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.search import html_base
from saler.providers.search.base import SearchItem
from saler.providers.search.html_base import BROWSER_UA_POOL, HTMLSearchEngine

FAKE_URL = "https://fake.example/search"

PAGE_OK = (
    '<html><body><div class="result-block" data-url="https://a.example/">A 站</div>'
    '<div class="result-block" data-url="https://b.example/">B 站</div></body></html>'
)
PAGE_EMPTY = '<html><body><div class="RESULT-LIST">没有找到相关结果</div></body></html>'
PAGE_BROKEN = "<html><body><p>nothing here</p></body></html>"


class FakeEngine(HTMLSearchEngine):
    """最小可用引擎：result-block 容器 + data-url 条目（模拟真实引擎的 hook 实现）。"""

    type_key = "fake_html"
    DEFAULT_BASE = FAKE_URL

    def _build_request(self, *, query, count, lang, country):
        return self._base_url, {"q": query, "n": count}, {}

    def _results_container_present(self, text: str) -> bool:
        return "result-block" in text or "RESULT-LIST" in text

    def _parse(self, text: str) -> list[SearchItem]:
        tree = LexborHTMLParser(text)
        items: list[SearchItem] = []
        for node in tree.css("div.result-block"):
            items.append(
                SearchItem(
                    title=node.text(strip=True),
                    url=(node.attributes or {}).get("data-url", ""),
                )
            )
        return [i for i in items if i.url]


class BoomEngine(FakeEngine):
    """容器存在但解析异常（模拟页面改版 → parse 类别）。"""

    type_key = "boom_html"

    def _parse(self, text: str) -> list[SearchItem]:
        raise ValueError("layout changed")


class MarkerEngine(FakeEngine):
    """带风控标记判定（模拟各引擎的 _check_blocked）。"""

    type_key = "marker_html"

    def _check_blocked(self, resp: httpx.Response) -> None:
        if "verify-me" in resp.text:
            raise ProviderError(ErrorKind.BLOCKED, "人机校验页", provider=self.type_key)


def _engine(cls=FakeEngine):
    return cls(params={"interval_s": 0})


class TestSearchFlow:
    @respx.mock
    def test_parses_results_with_title_and_url(self):
        respx.get(FAKE_URL).mock(return_value=httpx.Response(200, text=PAGE_OK))
        items = _engine().search(query="q", count=5)
        assert [i.title for i in items] == ["A 站", "B 站"]
        assert items[0].url == "https://a.example/"

    @respx.mock
    def test_legit_empty_returns_empty_list(self):
        respx.get(FAKE_URL).mock(return_value=httpx.Response(200, text=PAGE_EMPTY))
        assert _engine().search(query="q") == []

    @respx.mock
    def test_container_missing_is_blocked(self):
        respx.get(FAKE_URL).mock(return_value=httpx.Response(200, text=PAGE_BROKEN))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="q")
        assert ei.value.kind == ErrorKind.BLOCKED

    @respx.mock
    def test_parse_failure_is_parse_kind(self):
        respx.get(FAKE_URL).mock(return_value=httpx.Response(200, text=PAGE_OK))
        with pytest.raises(ProviderError) as ei:
            _engine(BoomEngine).search(query="q")
        assert ei.value.kind == ErrorKind.PARSE

    @respx.mock
    def test_blocked_marker_hook(self):
        respx.get(FAKE_URL).mock(return_value=httpx.Response(200, text="<html>verify-me</html>"))
        with pytest.raises(ProviderError) as ei:
            _engine(MarkerEngine).search(query="q")
        assert ei.value.kind == ErrorKind.BLOCKED


class TestHTTPStatusMapping:
    @respx.mock
    def test_429_is_rate_limit(self):
        respx.get(FAKE_URL).mock(return_value=httpx.Response(429))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="q")
        assert ei.value.kind == ErrorKind.RATE_LIMIT

    @respx.mock
    def test_403_is_blocked(self):
        respx.get(FAKE_URL).mock(return_value=httpx.Response(403))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="q")
        assert ei.value.kind == ErrorKind.BLOCKED

    @respx.mock
    def test_503_is_server(self):
        respx.get(FAKE_URL).mock(return_value=httpx.Response(503))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="q")
        assert ei.value.kind == ErrorKind.SERVER


class TestThrottleAndHeaders:
    @respx.mock
    def test_min_interval_between_requests(self, monkeypatch):
        clock = {"t": 0.0}
        sleeps: list[float] = []
        monkeypatch.setattr(html_base, "monotonic", lambda: clock["t"])
        monkeypatch.setattr(html_base, "sleep", lambda s: (sleeps.append(s), clock.__setitem__("t", clock["t"] + s)))
        monkeypatch.setattr(html_base.random, "uniform", lambda a, b: 0.0)  # 抖动归零 → 断言精确
        respx.get(FAKE_URL).mock(return_value=httpx.Response(200, text=PAGE_OK))
        eng = FakeEngine(params={"interval_s": 0.2})
        eng.search(query="q1")
        eng.search(query="q2")
        assert sleeps == [0.2]  # 首次不节流；第二次间隔 = 设定值

    @respx.mock
    def test_ua_from_browser_pool_and_accept_language(self):
        route = respx.get(FAKE_URL).mock(return_value=httpx.Response(200, text=PAGE_OK))
        _engine().search(query="q")
        req = route.calls[0].request
        assert req.headers["User-Agent"] in BROWSER_UA_POOL
        assert req.headers["Accept-Language"] == "en-US,en;q=0.9"

    @respx.mock
    def test_session_client_persists_cookies(self):
        route = respx.get(FAKE_URL).mock(
            side_effect=[
                httpx.Response(200, text=PAGE_OK, headers={"Set-Cookie": "BAIDUID=seed; Path=/"}),
                httpx.Response(200, text=PAGE_OK),
            ]
        )
        eng = FakeEngine(params={"interval_s": 0})
        eng.search(query="q1")
        eng.search(query="q2")
        assert "BAIDUID=seed" in route.calls[1].request.headers.get("Cookie", "")


class TestConnection:
    @respx.mock
    def test_ok(self):
        respx.get(FAKE_URL).mock(return_value=httpx.Response(200, text=PAGE_OK))
        result = _engine().test_connection()
        assert result.ok and result.detail == "连接成功"

    @respx.mock
    def test_fail_detail_carries_kind(self):
        respx.get(FAKE_URL).mock(return_value=httpx.Response(403))
        result = _engine().test_connection()
        assert not result.ok
        assert "[blocked]" in result.detail
