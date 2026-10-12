"""T204 契约测试：Bing 网页解析渠道（RSS 优先 / HTML 回退 / ck-a 还原 / cn 重定向 / 静默 captcha）。

样本为合成 fixture（形状参照 research R4 与生态实证：Bing RSS 形态、ck/a 的 a1<base64url>、
静默 captcha 返回 HTTP 200）。
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from saler.providers.errors import ErrorKind, ProviderError

BING_URL = "https://www.bing.com/search"
WWW4_URL = "https://www4.bing.com/search"
CN_URL = "https://cn.bing.com/search"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "search_pages" / "bing"

EMPTY_RSS = (
    '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>q</title></channel></rss>'
)
NO_RESULT_HTML = '<html><body><ol id="b_results"><li class="b_no">没有与此相关的结果</li></ol></body></html>'
BLANK_HTML = "<html><body><p>blank</p></body></html>"


def fx(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _engine():
    from saler.providers.search.bing import BingHTMLEngine

    return BingHTMLEngine(params={"interval_s": 0})


class TestBingRSSForm:
    @respx.mock
    def test_rss_preferred_with_direct_links(self):
        route = respx.get(BING_URL).mock(
            return_value=httpx.Response(200, text=fx("rss.xml"), headers={"Content-Type": "text/xml"})
        )
        items = _engine().search(query="q", count=5)
        assert route.calls[0].request.url.params["format"] == "rss"
        assert [i.title for i in items] == ["Rust 官网", "Rust 论坛"]
        assert items[0].url == "https://rust-lang.org/"
        assert items[1].snippet == "社区论坛 & 问答"
        assert len(route.calls) == 1  # RSS 有结果 → 不走 HTML 形态

    @respx.mock
    def test_rss_empty_falls_back_to_html_with_ensearch_cookie(self):
        def handler(request):
            if request.url.params.get("format") == "rss":
                return httpx.Response(200, text=EMPTY_RSS, headers={"Content-Type": "text/xml"})
            return httpx.Response(200, text=fx("results.html"))

        route = respx.get(BING_URL).mock(side_effect=handler)
        items = _engine().search(query="q")
        assert [i.title for i in items] == ["HTML 结果一", "HTML 直链二"]
        html_calls = [c for c in route.calls if c.request.url.params.get("format") != "rss"]
        assert len(html_calls) == 1
        assert "ENSEARCH=BENVER=1" in html_calls[0].request.headers.get("Cookie", "")


class TestBingHTMLForm:
    @respx.mock
    def test_ck_a_decoded_and_direct_link_kept(self):
        def handler(request):
            if request.url.params.get("format") == "rss":
                return httpx.Response(200, text=EMPTY_RSS)
            return httpx.Response(200, text=fx("results.html"))

        respx.get(BING_URL).mock(side_effect=handler)
        items = _engine().search(query="q")
        assert items[0].url == "https://html.bingresults.example/"  # ck/a → 离线还原
        assert items[1].url == "https://direct.example/page"  # 直链原样
        assert items[0].snippet == "摘要一"

    @respx.mock
    def test_no_results_page_is_legal_empty(self):
        def handler(request):
            if request.url.params.get("format") == "rss":
                return httpx.Response(200, text=EMPTY_RSS)
            return httpx.Response(200, text=NO_RESULT_HTML)

        respx.get(BING_URL).mock(side_effect=handler)
        assert _engine().search(query="q") == []


class TestBingBlocked:
    @respx.mock
    def test_silent_captcha_200_is_blocked(self):
        respx.get(BING_URL).mock(return_value=httpx.Response(200, text=fx("captcha.html")))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="q")
        assert ei.value.kind == ErrorKind.BLOCKED

    @respx.mock
    def test_blank_page_without_container_is_blocked(self):
        def handler(request):
            if request.url.params.get("format") == "rss":
                return httpx.Response(200, text=EMPTY_RSS)
            return httpx.Response(200, text=BLANK_HTML)

        respx.get(BING_URL).mock(side_effect=handler)
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="q")
        assert ei.value.kind == ErrorKind.BLOCKED


class TestBingGeoRedirect:
    @respx.mock
    def test_cn_redirect_retried_once_via_www4(self):
        respx.get(BING_URL).mock(return_value=httpx.Response(302, headers={"Location": CN_URL}))
        respx.get(CN_URL).mock(return_value=httpx.Response(200, text=fx("cn_redirect.html")))
        www4 = respx.get(WWW4_URL).mock(return_value=httpx.Response(200, text=fx("results.html")))
        items = _engine().search(query="q")
        assert www4.called
        assert items[0].url == "https://html.bingresults.example/"

    @respx.mock
    def test_cn_redirect_after_retry_is_blocked(self):
        respx.get(BING_URL).mock(return_value=httpx.Response(302, headers={"Location": CN_URL}))
        respx.get(CN_URL).mock(return_value=httpx.Response(200, text=fx("cn_redirect.html")))
        respx.get(WWW4_URL).mock(return_value=httpx.Response(302, headers={"Location": CN_URL}))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="q")
        assert ei.value.kind == ErrorKind.BLOCKED
        assert "cn.bing.com" in str(ei.value)


class TestBingManifest:
    def test_registered_with_preset(self):
        import saler.providers.search  # noqa: F401
        from saler.providers.registry import registry

        m = registry.get("search", "bing_html")
        assert m is not None and m.preset is not None
        assert m.secret_fields == ()
        assert m.preset["access_mode"] == "html"
        assert m.preset["apply_url"] is None
        assert m.preset["risk"]
