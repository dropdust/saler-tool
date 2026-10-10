"""API 依赖：会话注入与分页。"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Query, Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    with factory() as session:
        yield session


def pagination(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> tuple[int, int]:
    return page, page_size


def paginate(query, page: int, page_size: int) -> dict:
    total = query.order_by(None).count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}
