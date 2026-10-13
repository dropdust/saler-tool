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


# PyInstaller pyi_rth_gtk 钩子写入的 GTK/Pango 定位变量（取值 = 包内 _internal/）
_BUNDLE_GTK_ENV_VARS = (
    "GTK_EXE_PREFIX",
    "GTK_DATA_PREFIX",
    "GTK_PATH",
    "PANGO_LIBDIR",
    "PANGO_SYSCONFDIR",
)


def drop_bundle_gtk_env() -> list[str]:
    """移除指向包内目录的 GTK/Pango 定位变量，恢复系统 GTK 模块解析（T197）。

    根因：PyInstaller 的 pyi_rth_gtk 运行时钩子把上述变量都设为 sys._MEIPASS
    （_internal/），但冻结包并不携带 GTK 模块目录（lib/gtk-3.0/.../immodules）。
    Ubuntu 的 GTK3 依据 GTK_EXE_PREFIX 推导模块根（<prefix>/lib/gtk-3.0/3.0.0/
    immodules），于是 GTK 只搜包内不存在的路径——输入法模块（im-wayland.so）
    永远加载不了，中文输入全部失效（同源症状还有 "Failed to load module
    \"canberra-gtk-module\""）。移除这些变量后 GTK 回退到编译期系统路径，
    输入法模块从 /usr/lib/x86_64-linux-gnu/gtk-3.0/3.0.0/immodules 正常加载。

    只移除「取值指向包内目录」的变量（整个取值含任一路径项落在 _MEIPASS 即移除）；
    非冻结运行（无 _MEIPASS）或用户自设的其它取值一律不动。返回被移除的变量名。
    """
    import sys

    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return []
    bundle = os.path.abspath(meipass)
    removed: list[str] = []
    for var in _BUNDLE_GTK_ENV_VARS:
        value = os.environ.get(var)
        if not value:
            continue
        parts = [os.path.abspath(part) for part in value.split(os.pathsep) if part]
        if any(part == bundle or part.startswith(bundle + os.sep) for part in parts):
            os.environ.pop(var, None)
            removed.append(var)
    return removed


def _icon_path() -> str | None:
    """窗口图标（chanzi.png，T176）；缺失时返回 None——不阻断启动。

    pywebview 的 icon 参数仅 GTK/QT 有效（Linux 命中）；Windows/macOS 的
    窗口图标由各自壳/打包流程处理（见 packaging/README）。
    """
    import sys

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / "packaging" / "icon.png"
    else:
        # 开发态：backend/src/saler/desktop/app.py → <repo>/packaging/icon.png
        candidate = Path(__file__).resolve().parents[3].parent / "packaging" / "icon.png"
    return str(candidate) if candidate.is_file() else None


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


def main(argv: list[str] | None = None) -> int:
    drop_bundle_gtk_env()  # T197：必须在任何 GTK/WebView 初始化之前恢复系统模块解析

    import argparse

    from saler.desktop.diagnostics import check_desktop_environment, friendly_startup_error
    from saler.logging_config import setup_logging
    from saler.services.datadir import resolve_data_dir
    from saler.services.proxy import apply_loopback_bypass

    parser = argparse.ArgumentParser(description="销售获客工具（本地桌面 / 服务）")
    parser.add_argument("--server", action="store_true", help="仅启动本地 API（无窗口），打印访问地址")
    parser.add_argument("--port", type=int, default=0, help="--server 模式端口（默认自动分配）")
    args = parser.parse_args(argv)

    apply_loopback_bypass()  # T135：回环流量绕过系统代理
    if not args.server:
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

    if args.server:
        return _run_server(app, token, data_dir=data_dir, port=args.port)

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
        webview.start(icon=_icon_path())
    except Exception as exc:  # noqa: BLE001 —— WebView 运行时缺失等给出可操作提示（T134）
        logger.exception("桌面窗口启动失败")
        _report_fatal(friendly_startup_error(exc))
        return 4
    finally:
        server.stop()
    return 0


def _run_server(app, token: str, *, data_dir: Path, port: int) -> int:
    """无窗服务模式（冒烟/无 GUI 环境）：阻塞运行本地 API，并把访问地址写入数据目录。"""
    import socket

    import uvicorn

    if not port:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}/?token={token}"
    try:
        (Path(data_dir) / "server_url.txt").write_text(url + "\n", encoding="utf-8")
    except OSError:
        pass
    print(f"\n销售获客工具已启动（服务模式，无窗口）：\n  {url}\n按 Ctrl+C 退出\n", flush=True)
    logger.info(f"服务模式启动：{url}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
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
