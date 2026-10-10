"""桌面入口：启动本地 API（127.0.0.1 随机端口）→ 健康检查 → 打开原生窗口。

- 端口协商：绑定 127.0.0.1:0 由系统分配，避免固定端口冲突；
- 令牌注入：URL 带 ?token=，前端一次读取后转存（SSE 也用查询参数）；
- 关窗即停服务（防孤儿进程）。
开发期可用 ``SALER_DEV_URL``（如 http://localhost:5173）直接指向 Vite 开发服务器。
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import httpx
from loguru import logger

WINDOW_TITLE = "销售获客工具"


def _frontend_dist() -> Path:
    import sys

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "frontend" / "dist"
    # 开发态：backend/src/saler/desktop/app.py → <repo>/frontend/dist
    return Path(__file__).resolve().parents[3].parent / "frontend" / "dist"


class ServerThread(threading.Thread):
    """在后台线程运行 uvicorn（端口 0 = 系统分配）。"""

    def __init__(self, app, host: str = "127.0.0.1") -> None:
        super().__init__(daemon=True, name="saler-api")
        import uvicorn

        self._server = uvicorn.Server(uvicorn.Config(app, host=host, port=0, log_level="warning"))

    def run(self) -> None:
        self._server.run()

    def wait_port(self, timeout: float = 15.0) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            servers = getattr(self._server, "servers", None) or []
            if servers and servers[0].sockets:
                return servers[0].sockets[0].getsockname()[1]
            time.sleep(0.05)
        raise RuntimeError("本地服务启动超时")

    def stop(self) -> None:
        self._server.should_exit = True


def wait_health(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    # trust_env=False：回环地址绕过系统代理（no_proxy 语义，T135 同款）
    with httpx.Client(trust_env=False, timeout=2.0) as client:
        while time.monotonic() < deadline:
            try:
                resp = client.get(f"http://127.0.0.1:{port}/api/v1/health")
                if resp.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
    raise RuntimeError("本地 API 健康检查超时")


def _build_app(data_dir: Path):
    from sqlalchemy.orm import sessionmaker

    from saler.api.main import create_app
    from saler.db.session import make_engine
    from saler.jobs.maintenance import run_maintenance
    from saler.security.crypto import resolve_secret_box
    from saler.security.token import AppToken
    from saler.services.datadir import check_writable, db_path, ensure_layout
    from saler.services.migrations import run_migrations

    ok, message = check_writable(data_dir)
    if not ok:
        raise RuntimeError(f"数据目录不可用：{message}")
    ensure_layout(data_dir)
    resolve_secret_box(data_dir)
    db_url = f"sqlite:///{db_path(data_dir)}"
    run_migrations(db_url)
    engine = make_engine(db_path(data_dir))
    try:  # 启动维护（T136）：日志滚动清理 + 备份提醒；失败不阻断启动
        with sessionmaker(bind=engine)() as db:
            run_maintenance(db)
    except Exception:  # noqa: BLE001
        logger.exception("启动维护任务失败（忽略，不影响使用）")
    token = AppToken()
    dist = _frontend_dist()
    if not dist.is_dir() and not os.environ.get("SALER_DEV_URL"):
        logger.warning(
            f"未找到前端产物 {dist}：请先执行 `cd frontend && pnpm build`，"
            "或设置 SALER_DEV_URL 指向 Vite 开发服务器"
        )
    return create_app(engine=engine, token=token.value, frontend_dist=dist), token.value


def main() -> int:
    from saler.desktop.diagnostics import check_desktop_environment, friendly_startup_error
    from saler.logging_config import setup_logging
    from saler.services.datadir import resolve_data_dir
    from saler.services.proxy import apply_loopback_bypass

    apply_loopback_bypass()  # T135：回环流量绕过系统代理
    diagnosis = check_desktop_environment()
    if not diagnosis.ok:
        logger.warning(f"桌面环境自检未通过：{diagnosis.detail}。{diagnosis.hint}")

    data_dir = resolve_data_dir()
    try:
        setup_logging(data_dir)
        app, token = _build_app(data_dir)
    except Exception as exc:  # noqa: BLE001 - 启动失败需可见
        logger.exception("桌面应用启动失败")
        _report_fatal(f"启动失败：{exc}")
        return 2

    server = ServerThread(app)
    server.start()
    try:
        port = server.wait_port()
        wait_health(port)
    except Exception as exc:  # noqa: BLE001
        logger.exception("本地服务启动失败")
        server.stop()
        _report_fatal(f"本地服务启动失败：{exc}")
        return 3

    url = os.environ.get("SALER_DEV_URL") or f"http://127.0.0.1:{port}/?token={token}"
    logger.info(f"桌面壳加载 {url}")

    import webview

    webview.create_window(WINDOW_TITLE, url, width=1360, height=900, min_size=(1024, 700))
    try:
        webview.start()
    except Exception as exc:  # noqa: BLE001 —— WebView 运行时缺失等给出可操作提示（T134）
        logger.exception("桌面窗口启动失败")
        _report_fatal(friendly_startup_error(exc))
        return 4
    finally:
        server.stop()
    return 0


def _report_fatal(message: str) -> None:
    try:
        import webview

        webview.create_window(WINDOW_TITLE, html=f"<h3>{message}</h3>")
        webview.start()
    except Exception:
        print(message)


if __name__ == "__main__":
    raise SystemExit(main())
