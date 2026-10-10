"""桌面壳 SPA 静态托管（T020-fix 回归）：提供产物时 `/` 返回 index.html，且不遮蔽 API。"""

from __future__ import annotations


def test_spa_mounted_when_dist_provided(tmp_path, engine, session_factory, data_dir):
    from fastapi.testclient import TestClient

    from saler.api.main import create_app

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>saler-spa</body></html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")

    app = create_app(
        engine=engine,
        session_factory=session_factory,
        token="spa-token",
        data_dir=data_dir,
        frontend_dist=dist,
    )
    with TestClient(app, headers={"X-App-Token": "spa-token"}) as client:
        index = client.get("/")
        assert index.status_code == 200
        assert "saler-spa" in index.text
        asset = client.get("/assets/app.js")
        assert asset.status_code == 200 and "console.log" in asset.text
        # 静态挂载不得遮蔽 API 路由
        health = client.get("/api/v1/health")
        assert health.status_code == 200 and health.json()["ok"] is True


def test_no_mount_without_dist(client):
    # 未提供产物：根路径 404（开发时用 SALER_DEV_URL 指向 Vite）
    assert client.get("/").status_code == 404


def test_missing_dist_dir_is_ignored(tmp_path, engine, session_factory, data_dir):
    from fastapi.testclient import TestClient

    from saler.api.main import create_app

    app = create_app(
        engine=engine,
        session_factory=session_factory,
        token="t",
        data_dir=data_dir,
        frontend_dist=tmp_path / "not-built",
    )
    with TestClient(app, headers={"X-App-Token": "t"}) as client:
        assert client.get("/").status_code == 404
        assert client.get("/api/v1/health").status_code == 200
