"""T208 契约测试：Google 网页解析渠道（/url?q= 离线 / /goto 跟随一次 / 正文嗅探风控 / 广告过滤）。

样本为合成 fixture（形状参照 research R3：/url?q= 离线解码、/goto?url=<签名> 需跟随一次 302、
sorry 落地与 unusual traffic 正文标记、data-text-ad/aclk 广告标记；`num=` 已失效不使用）。
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from saler.providers.errors import ErrorKind, ProviderError

GOOGLE_URL = "https://www.google.com/search"
SORRY_URL = "https://www.google.com/sorry/index"
GOTO_URL = "https://www.google.com/goto?url=CAESabcdef"
GOTO_TARGET = "https://signed-target.example/landing"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "search_pages" / "google"

NO_RESULT_HTML = (
    '<html><body><div id="search"><div id="rso">'
    "<p>找不到与您的查询相符的结果。</p>"
    "</div></div></body></html>"
)
BLANK_HTML = "<html><body><p>blank</p></body></html>"


def fx(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _engine():
    from saler.providers.search.google import GoogleHTMLEngine

    return GoogleHTMLEngine(params={"interval_s": 0})


class TestGoogleParse:
    @respx.mock
    def test_url_q_decode_direct_kept_ads_skipped_and_no_num_param(self):
        route = respx.get(GOOGLE_URL).mock(return_value=httpx.Response(200, text=fx("results.html")))
        items = _engine().search(query="global market")
        req = route.calls[0].request
        assert "num" not in req.url.params  # num 已失效：不使用
        assert "CONSENT=" in req.headers.get("Cookie", "")  # consent 绕过
        assert [i.title for i in items] == ["全局市场方案", "直链结果"]
        assert items[0].url == "https://global.example/solutions?utm=1"  # /url?q= 离线还原
        assert items[1].url == "https://direct-global.example/page"
        assert items[0].snippet == "面向全球市场的解决方案。"

    @respx.mock
    def test_no_result_page_is_legal_empty(self):
        respx.get(GOOGLE_URL).mock(return_value=httpx.Response(200, text=NO_RESULT_HTML))
        assert _engine().search(query="x") == []

    @respx.mock
    def test_container_missing_is_blocked(self):
        respx.get(GOOGLE_URL).mock(return_value=httpx.Response(200, text=BLANK_HTML))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="x")
        assert ei.value.kind == ErrorKind.BLOCKED


class TestGoogleGoto:
    @respx.mock
    def test_goto_followed_once_to_target(self):
        respx.get(GOOGLE_URL).mock(return_value=httpx.Response(200, text=fx("goto_results.html")))
        respx.get(GOTO_URL).mock(return_value=httpx.Response(302, headers={"Location": GOTO_TARGET}))
        respx.get(GOTO_TARGET).mock(return_value=httpx.Response(200, text="<html>ok</html>"))
        items = _engine().search(query="x")
        assert items[0].title == "签名跳转结果"
        assert items[0].url == GOTO_TARGET

    @respx.mock
    def test_goto_unresolvable_item_dropped(self):
        respx.get(GOOGLE_URL).mock(return_value=httpx.Response(200, text=fx("goto_results.html")))
        respx.get(GOTO_URL).mock(return_value=httpx.Response(404))
        assert _engine().search(query="x") == []  # 无法还原 → 丢弃该条（FR-004 边界）


class TestGoogleBlocked:
    @respx.mock
    def test_sorry_landing_is_blocked(self):
        respx.get(GOOGLE_URL).mock(return_value=httpx.Response(302, headers={"Location": SORRY_URL}))
        respx.get(SORRY_URL).mock(return_value=httpx.Response(200, text=fx("sorry.html")))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="x")
        assert ei.value.kind == ErrorKind.BLOCKED

    @respx.mock
    def test_body_sniff_unusual_traffic_is_blocked(self):
        respx.get(GOOGLE_URL).mock(return_value=httpx.Response(200, text=fx("unusual_traffic.html")))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="x")
        assert ei.value.kind == ErrorKind.BLOCKED

    @respx.mock
    def test_body_sniff_chinese_marker_is_blocked(self):
        respx.get(GOOGLE_URL).mock(return_value=httpx.Response(200, text=fx("sorry.html")))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="x")
        assert ei.value.kind == ErrorKind.BLOCKED

    @respx.mock
    def test_429_is_rate_limit(self):
        respx.get(GOOGLE_URL).mock(return_value=httpx.Response(429))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="x")
        assert ei.value.kind == ErrorKind.RATE_LIMIT


class TestGoogleManifest:
    def test_registered_with_high_risk_preset(self):
        import saler.providers.search  # noqa: F401
        from saler.providers.registry import registry

        m = registry.get("search", "google_html")
        assert m is not None and m.preset is not None
        assert m.secret_fields == ()
        assert m.preset["access_mode"] == "html"
        assert m.preset["apply_url"] is None
        assert "高风险" in m.preset["risk"] or "尽力而为" in m.preset["risk"]
