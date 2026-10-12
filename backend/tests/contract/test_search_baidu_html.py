"""T205 契约测试：百度网页解析渠道（mu 离线还原 / cookie 配对 / 安全验证识别 / 广告过滤）。

样本为合成 fixture（形状参照 research R2：mu/data-landurl 离线还原、wappass 落地与
"百度安全验证"标题标记、HTTP 480 验证码状态）。
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from saler.providers.errors import ErrorKind, ProviderError

BAIDU_HOME = "https://www.baidu.com/"
BAIDU_S = "https://www.baidu.com/s"
WAPPASS = "https://wappass.baidu.com/static/captcha"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "search_pages" / "baidu"

NO_RESULT_HTML = (
    '<html><head><title>x_百度搜索</title></head><body>'
    '<div id="content_left"><p class="nors">很抱歉，没有找到与"x"相关的网页。</p></div>'
    "</body></html>"
)
BLANK_HTML = "<html><body><p>blank</p></body></html>"


def fx(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _engine():
    from saler.providers.search.baidu import BaiduHTMLEngine

    return BaiduHTMLEngine(params={"interval_s": 0})


def _mock_home():
    return respx.get(BAIDU_HOME).mock(
        return_value=httpx.Response(200, text="<html>home</html>", headers={"Set-Cookie": "BAIDUID=seed; Path=/"})
    )


class TestBaiduParse:
    @respx.mock
    def test_mu_and_landurl_decode_ads_skipped(self):
        _mock_home()
        respx.get(BAIDU_S).mock(return_value=httpx.Response(200, text=fx("results.html")))
        items = _engine().search(query="紧固件 采购")
        assert [i.title for i in items] == ["示例招聘公司", "备用属性公司"]
        assert items[0].url == "https://zhaopin.example.com/about"  # mu 离线还原
        assert items[1].url == "https://fallback.example.com/"  # data-landurl 备用
        assert items[0].snippet.startswith("紧固件采购企业")

    @respx.mock
    def test_no_result_page_is_legal_empty(self):
        _mock_home()
        respx.get(BAIDU_S).mock(return_value=httpx.Response(200, text=NO_RESULT_HTML))
        assert _engine().search(query="x") == []

    @respx.mock
    def test_container_missing_is_blocked(self):
        _mock_home()
        respx.get(BAIDU_S).mock(return_value=httpx.Response(200, text=BLANK_HTML))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="x")
        assert ei.value.kind == ErrorKind.BLOCKED


class TestBaiduSession:
    @respx.mock
    def test_cookie_seeded_once_and_ua_fixed(self):
        home = _mock_home()
        search = respx.get(BAIDU_S).mock(return_value=httpx.Response(200, text=fx("results.html")))
        eng = _engine()
        eng.search(query="q1")
        eng.search(query="q2")
        assert len(home.calls) == 1  # 仅首次种 BAIDUID
        assert "BAIDUID=seed" in search.calls[0].request.headers.get("Cookie", "")
        ua1 = search.calls[0].request.headers["User-Agent"]
        ua2 = search.calls[1].request.headers["User-Agent"]
        assert ua1 == ua2  # cookie 与 UA 配对：实例内固定
        assert "Mozilla" in ua1  # 桌面浏览器 UA（非工具自述 UA）
        assert search.calls[0].request.headers["Accept-Language"].startswith("zh-CN")


class TestBaiduBlocked:
    @respx.mock
    def test_verify_title_marker_is_blocked(self):
        _mock_home()
        respx.get(BAIDU_S).mock(return_value=httpx.Response(200, text=fx("verify.html")))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="x")
        assert ei.value.kind == ErrorKind.BLOCKED

    @respx.mock
    def test_landing_wappass_is_blocked(self):
        _mock_home()
        respx.get(BAIDU_S).mock(return_value=httpx.Response(302, headers={"Location": WAPPASS}))
        respx.get(WAPPASS).mock(return_value=httpx.Response(200, text=fx("verify.html")))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="x")
        assert ei.value.kind == ErrorKind.BLOCKED

    @respx.mock
    def test_http_480_is_blocked(self):
        _mock_home()
        respx.get(BAIDU_S).mock(return_value=httpx.Response(480, text=fx("http480.html")))
        with pytest.raises(ProviderError) as ei:
            _engine().search(query="x")
        assert ei.value.kind == ErrorKind.BLOCKED


class TestBaiduManifest:
    def test_registered_with_preset(self):
        import saler.providers.search  # noqa: F401
        from saler.providers.registry import registry

        m = registry.get("search", "baidu_html")
        assert m is not None and m.preset is not None
        assert m.secret_fields == ()
        assert m.preset["access_mode"] == "html"
        assert m.preset["apply_url"] is None
        assert "中文" in m.preset["market"]
