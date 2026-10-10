"""代理兼容（T135）：回环地址绕过系统代理（no_proxy 语义）。

- 本地 API 与桌面壳均走 127.0.0.1：系统代理（含企业 PAC）不得劫持回环流量；
- 抓取/检索等外部请求使用显式代理配置（httpx trust_env=False），不受影响；
- 启动时调用 `apply_loopback_bypass()`，把回环名合并进 NO_PROXY/no_proxy 环境变量，
  对可能读取环境变量的子进程/库同样生效。
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def loopback_bypass_value(existing: str | None = None) -> str:
    """把回环名合并进既有 NO_PROXY 值（保留用户已有配置，去重）。"""
    parts = [item.strip() for item in (existing or "").split(",") if item.strip()]
    for host in LOOPBACK_HOSTS:
        if host not in parts:
            parts.append(host)
    return ",".join(parts)


def apply_loopback_bypass(env: MutableMapping[str, str] | None = None) -> str:
    """启动时调用：设置 NO_PROXY 与 no_proxy（大小写两种），返回最终值。"""
    target = env if env is not None else os.environ
    value = loopback_bypass_value(target.get("NO_PROXY") or target.get("no_proxy"))
    target["NO_PROXY"] = value
    target["no_proxy"] = value
    return value
