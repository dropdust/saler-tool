"""领域层错误（API 层映射为 {code,message,details} 包）。"""

from __future__ import annotations


class DomainError(Exception):
    """领域层错误基类。"""


class NotFound(DomainError):
    pass


class Duplicate(DomainError):
    pass


class ValidationFailed(DomainError):
    pass


class LLMNotConfigured(DomainError):
    """尚未配置大模型服务（S2 前使用 AI 功能时提示）。"""
