"""Provider 适配器注册表（contracts/provider-adapters.md §5）。

新增提供方 = 实现接口 + 注册 manifest（约定大于配置：前端按 config_schema 动态渲染表单）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderManifest:
    kind: str  # llm / search / mail / sms
    type_key: str
    display_name: str
    config_schema: dict = field(default_factory=dict)  # JSON Schema（前端动态表单）
    secret_fields: tuple[str, ...] = ()
    factory: Callable[..., Any] | None = None


class ProviderRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], ProviderManifest] = {}

    def register(self, manifest: ProviderManifest) -> None:
        self._items[(manifest.kind, manifest.type_key)] = manifest

    def get(self, kind: str, type_key: str) -> ProviderManifest | None:
        return self._items.get((kind, type_key))

    def by_kind(self, kind: str) -> list[ProviderManifest]:
        return [m for (k, _), m in sorted(self._items.items()) if k == kind]


registry = ProviderRegistry()
