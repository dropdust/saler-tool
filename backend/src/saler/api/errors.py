"""API 错误包：{code, message, details}（contracts/local-api.md 通用约定）。"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def bad_request(message: str, code: str = "bad_request") -> ApiError:
    return ApiError(400, code, message)


def not_found(what: str = "对象") -> ApiError:
    return ApiError(404, "not_found", f"{what}不存在")


def conflict(message: str, code: str = "conflict") -> ApiError:
    return ApiError(409, code, message)


def unprocessable(message: str, code: str = "unprocessable") -> ApiError:
    return ApiError(422, code, message)
