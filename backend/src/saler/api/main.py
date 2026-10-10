"""FastAPI 应用工厂。

- 仅绑定回环地址（由 desktop/uvicorn 层保证）；
- 中间件校验启动令牌：普通请求 `X-App-Token` 头，SSE 走 `?token=`（EventSource 限制）；
- 错误统一为 {code, message, details} 包（contracts/local-api.md）。
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from saler import __version__
from saler.api.errors import ApiError
from saler.api.routes import ai, graph, jobs, seeds, settings
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
from saler.security.token import AppToken

API_PREFIX = "/api/v1"


def create_app(
    *,
    engine=None,
    session_factory=None,
    token: str | None = None,
    job_manager: JobManager | None = None,
    data_dir=None,
) -> FastAPI:
    if session_factory is None:
        if engine is None:
            raise ValueError("create_app 需要 engine 或 session_factory")
        session_factory = make_session_factory(engine)

    app_token = AppToken(token)
    app = FastAPI(title="Saler 本地 API", version=__version__, docs_url=None, redoc_url=None)
    app.state.session_factory = session_factory
    app.state.token = app_token
    app.state.job_manager = job_manager or JobManager(session_factory)
    app.state.data_dir = data_dir

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
    app.include_router(graph.router, prefix=API_PREFIX)
    app.include_router(seeds.router, prefix=API_PREFIX)
    app.include_router(ai.router, prefix=API_PREFIX)
    return app
