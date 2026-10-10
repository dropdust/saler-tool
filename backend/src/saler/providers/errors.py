"""统一 Provider 错误分类（contracts/provider-adapters.md 通用约定）。"""

from __future__ import annotations

from enum import StrEnum


class ErrorKind(StrEnum):
    AUTH = "auth"                      # 凭证无效/过期
    QUOTA = "quota"                    # 配额/额度耗尽
    RATE_LIMIT = "rate_limit"          # 被限流（含 Retry-After）
    TIMEOUT = "timeout"                # 超时
    NETWORK = "network"                # 网络问题
    BLOCKED = "blocked"                # 被目标风控/拒答（检索特有）
    INVALID_OUTPUT = "invalid_output"  # 输出不符合 schema（LLM 特有）
    RECIPIENT_REJECTED = "recipient_rejected"  # 收件人被拒（发送特有）
    SERVER = "server"                  # 对端 5xx


RETRYABLE_KINDS = frozenset(
    {ErrorKind.RATE_LIMIT, ErrorKind.TIMEOUT, ErrorKind.NETWORK, ErrorKind.SERVER}
)


class ProviderError(Exception):
    def __init__(
        self,
        kind: ErrorKind | str,
        message: str,
        *,
        provider: str | None = None,
        retryable: bool | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind if isinstance(kind, ErrorKind) else ErrorKind(kind)
        self.provider = provider
        self.detail = detail
        self.retryable = self.kind in RETRYABLE_KINDS if retryable is None else retryable
