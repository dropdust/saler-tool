"""FastAPI 应用工厂。

- 仅绑定回环地址（由 desktop/uvicorn 层保证）；
- 中间件校验启动令牌：普通请求 `X-App-Token` 头，SSE 走 `?token=`（EventSource 限制）；
- 错误统一为 {code, message, details} 包（contracts/local-api.md）。
"""

from __future__ import annotations

import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from loguru import logger

from saler import __version__
from saler.api.errors import ApiError
from saler.api.routes import (
    ai,
    backup,
    campaigns,
    channels,
    companies,
    content,
    crawl,
    domains,
    exclusion_rules,
    graph,
    jobs,
    llm,
    search_providers,
    seeds,
    settings,
    suppressions,
)
from saler.core.errors import (
    DomainError,
    Duplicate,
    LLMNotConfigured,
    ValidationFailed,
)
from saler.core.errors import (
    NotFound as DomainNotFound,
)
from saler.db.session import make_session_factory
from saler.jobs.engine import JobManager
from saler.jobs.reconcile import reconcile_interrupted_jobs
from saler.security.token import AppToken
from saler.services import settings_service

API_PREFIX = "/api/v1"

_HTML_OPEN_RE = re.compile(r"<html\b([^>]*)>", re.IGNORECASE)


def _inject_theme_dark(html: str) -> str:
    """把 dark 类合并进 <html> 起始标签（002-frontend-theme，契约 §2）。

    未匹配到时原样返回并告警——前端启动同步（syncFromServer）会兜底校正。
    """

    def repl(match: re.Match[str]) -> str:
        attrs = match.group(1)
        class_match = re.search(r'class="([^"]*)"', attrs)
        if class_match:
            classes = f"{class_match.group(1)} dark".strip()
            attrs = attrs[: class_match.start()] + f'class="{classes}"' + attrs[class_match.end() :]
        else:
            attrs = f'{attrs} class="dark"'
        return f"<html{attrs}>"

    new_html, count = _HTML_OPEN_RE.subn(repl, html, count=1)
    if count == 0:
        logger.warning("index.html 未匹配 <html> 起始标签：主题注入跳过（前端启动同步兜底）")
        return html
    return new_html


def create_app(
    *,
    engine=None,
    session_factory=None,
    token: str | None = None,
    job_manager: JobManager | None = None,
    data_dir=None,
    frontend_dist=None,
) -> FastAPI:
    if session_factory is None:
        if engine is None:
            raise ValueError("create_app 需要 engine 或 session_factory")
        session_factory = make_session_factory(engine)

    app_token = AppToken(token)
    app = FastAPI(title="Saler 本地 API", version=__version__, docs_url=None, redoc_url=None)
    app.state.session_factory = session_factory
    app.state.engine = engine  # 供"恢复备份"等整库替换场景 dispose 用
    app.state.token = app_token
    app.state.job_manager = job_manager or JobManager(session_factory)
    app.state.data_dir = data_dir
    # 启动对账（005-T246）：进程退出遗留的非终态任务 → interrupted（只改状态、绝不自动重放）。
    # 四个入口（桌面 / --server / dev / 测试）都经本工厂，故此处覆盖即可。
    try:
        reconcile_interrupted_jobs(session_factory)
    except Exception:  # noqa: BLE001 - 对账失败不阻断启动（沿用启动维护的口径）
        logger.exception("启动对账失败（忽略，不影响使用）")

    @app.middleware("http")
    async def _auth_middleware(request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/") or path == f"{API_PREFIX}/health":
            return await call_next(request)
        candidate = request.headers.get("X-App-Token") or request.query_params.get("token")
        if not app_token.check(candidate):
            return JSONResponse(
                status_code=401,
                content={"code": "unauthorized", "message": "无效或缺失的启动令牌", "details": None},
            )
        return await call_next(request)

    @app.exception_handler(ApiError)
    async def _api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"code": exc.code, "message": exc.message, "details": exc.details},
        )

    @app.exception_handler(DomainError)
    async def _domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
        if isinstance(exc, LLMNotConfigured):
            status, code = 409, "llm_not_configured"
        elif isinstance(exc, Duplicate):
            status, code = 409, "conflict"
        elif isinstance(exc, DomainNotFound):
            status, code = 404, "not_found"
        elif isinstance(exc, ValidationFailed):
            status, code = 422, "unprocessable"
        else:
            status, code = 400, "domain_error"
        return JSONResponse(
            status_code=status,
            content={"code": code, "message": str(exc), "details": None},
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常")
        return JSONResponse(
            status_code=500,
            content={"code": "internal_error", "message": f"{type(exc).__name__}: {exc}", "details": None},
        )

    @app.get(f"{API_PREFIX}/health")
    async def health() -> dict:
        return {"ok": True, "version": __version__}

    app.include_router(jobs.router, prefix=API_PREFIX)
    app.include_router(settings.router, prefix=API_PREFIX)
    app.include_router(settings.logs_router, prefix=API_PREFIX)
    app.include_router(graph.router, prefix=API_PREFIX)
    app.include_router(seeds.router, prefix=API_PREFIX)
    app.include_router(ai.router, prefix=API_PREFIX)
    app.include_router(llm.router, prefix=API_PREFIX)
    app.include_router(backup.router, prefix=API_PREFIX)
    app.include_router(crawl.router, prefix=API_PREFIX)
    app.include_router(domains.router, prefix=API_PREFIX)
    app.include_router(companies.router, prefix=API_PREFIX)
    app.include_router(search_providers.router, prefix=API_PREFIX)
    app.include_router(exclusion_rules.router, prefix=API_PREFIX)
    app.include_router(channels.router, prefix=API_PREFIX)
    app.include_router(campaigns.router, prefix=API_PREFIX)
    app.include_router(suppressions.router, prefix=API_PREFIX)
    app.include_router(content.router, prefix=API_PREFIX)

    # 前端 SPA 静态托管（桌面壳加载；挂载在最后，不遮蔽 /api/v1 路由）
    if frontend_dist is not None:
        from pathlib import Path as _Path

        from fastapi.staticfiles import StaticFiles

        dist = _Path(frontend_dist)
        if dist.is_dir():
            index_file = dist / "index.html"
            if index_file.is_file():

                @app.get("/", include_in_schema=False)
                def spa_index() -> Response:
                    """HTML 入口：注入当前主题类实现首屏零闪变（FR-007，契约 §2）。

                    hash 路由下 HTML 入口唯一；读取失败一律按 light，不阻断启动（FR-006）。
                    """
                    html = index_file.read_text(encoding="utf-8")
                    try:
                        with session_factory() as session:
                            theme = settings_service.get(session, "ui_theme", "light")
                    except Exception:  # noqa: BLE001 —— 注入失败降级为 light，前端仍可校正
                        logger.warning("读取 ui_theme 失败：首屏按 light 返回")
                        theme = "light"
                    if theme == "dark":
                        html = _inject_theme_dark(html)
                    return Response(
                        content=html,
                        media_type="text/html",
                        headers={"Cache-Control": "no-store"},
                    )

            app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")
        else:
            logger.warning(f"未找到前端构建产物：{dist}（界面将 404；请先构建前端或用 SALER_DEV_URL）")
    return app
