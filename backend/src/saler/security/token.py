"""本地 API 启动令牌：每次启动随机生成，仅注入桌面壳。"""

from __future__ import annotations

import secrets as _secrets


class AppToken:
    def __init__(self, value: str | None = None) -> None:
        self.value = value or _secrets.token_urlsafe(32)

    def check(self, candidate: str | None) -> bool:
        return bool(candidate) and _secrets.compare_digest(candidate, self.value)
