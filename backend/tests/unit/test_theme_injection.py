"""T160 注入路由单测（002-frontend-theme）：GET / 首屏主题注入。

契约：contracts/theme-contract.md §2。
- KV=dark → HTML 的 <html> 起始标签注入 class="dark"（与既有 class 合并）；
- KV=light / 无行 / 非法值 → 原样返回（按 light）；
- 响应头 Cache-Control: no-store；/assets/* 不受影响；
- 无 dist 时 "/" 仍为 404（路由仅在有产物时注册）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from saler.api.main import create_app
from saler.services import settings_service

INDEX_HTML = '<!doctype html>\n<html lang="zh-CN">\n<head><title>t</title></head><body>x</body></html>\n'
INDEX_HTML_WITH_CLASS = '<!doctype html>\n<html lang="zh-CN" class="foo">\n<body>x</body></html>\n'


def _make_dist(tmp_path, index: str = INDEX_HTML):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(index, encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")
    return dist


def _make_client(engine, session_factory, data_dir, dist):
    app = create_app(
        engine=engine,
        session_factory=session_factory,
        token="t",
        data_dir=data_dir,
        frontend_dist=dist,
    )
    return TestClient(app, headers={"X-App-Token": "t"})


class TestThemeInjection:
    def test_dark_injected_into_html_open_tag(self, tmp_path, engine, session_factory, data_dir, db):
        settings_service.set_value(db, "ui_theme", "dark")
        with _make_client(engine, session_factory, data_dir, _make_dist(tmp_path)) as client:
            resp = client.get("/")
            assert resp.status_code == 200
            assert 'class="dark"' in resp.text
            assert '<html lang="zh-CN" class="dark">' in resp.text

    def test_dark_merges_with_existing_class(self, tmp_path, engine, session_factory, data_dir, db):
        settings_service.set_value(db, "ui_theme", "dark")
        dist = _make_dist(tmp_path, INDEX_HTML_WITH_CLASS)
        with _make_client(engine, session_factory, data_dir, dist) as client:
            resp = client.get("/")
            assert 'class="foo dark"' in resp.text

    def test_light_and_absent_and_invalid_keep_markup(self, tmp_path, engine, session_factory, data_dir, db):
        # 无行（默认 light）
        with _make_client(engine, session_factory, data_dir, _make_dist(tmp_path)) as client:
            resp = client.get("/")
            assert resp.text == INDEX_HTML
            assert "dark" not in resp.text

        # 显式 light
        settings_service.set_value(db, "ui_theme", "light")
        with _make_client(engine, session_factory, data_dir, _make_dist(tmp_path)) as client:
            assert client.get("/").text == INDEX_HTML

        # 非法值（手工改库）→ 按 light 原样
        settings_service.set_value(db, "ui_theme", "blue")
        with _make_client(engine, session_factory, data_dir, _make_dist(tmp_path)) as client:
            assert client.get("/").text == INDEX_HTML

    def test_no_store_header_and_assets_untouched(self, tmp_path, engine, session_factory, data_dir, db):
        settings_service.set_value(db, "ui_theme", "dark")
        with _make_client(engine, session_factory, data_dir, _make_dist(tmp_path)) as client:
            index = client.get("/")
            assert index.headers["cache-control"] == "no-store"
            assert index.headers["content-type"].startswith("text/html")
            asset = client.get("/assets/app.js")
            assert asset.status_code == 200 and "console.log" in asset.text

    def test_root_404_without_dist(self, client):
        # 无产物：不注册注入路由，根路径保持 404（与 test_spa_mount 语义一致）
        assert client.get("/").status_code == 404
