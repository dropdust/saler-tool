"""内容变量渲染（contracts/data-exchange.md §5；FR-035/039）。

语法 ``{{variable_name}}``；未知/缺值变量渲染为空并在预览中告警（不阻断发布，由人决定）。
"""

from __future__ import annotations

import re

VARIABLE_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

BUILTIN_VARIABLES = (
    "company_name",
    "contact_name",
    "country",
    "language",
    "sender_name",
    "signature",
    "today",
)


def parse_variables(text: str) -> list[str]:
    """按出现顺序返回去重的小写变量名。"""
    found: list[str] = []
    for match in VARIABLE_RE.finditer(text or ""):
        name = match.group(1).lower()
        if name not in found:
            found.append(name)
    return found


def render(template: str, variables: dict[str, str | None]) -> tuple[str, list[str]]:
    """返回 (渲染结果, 告警列表)；缺失/未知变量渲染为空并告警。"""
    warnings: list[str] = []

    def _substitute(match: re.Match) -> str:
        name = match.group(1).lower()
        value = variables.get(name)
        if value in (None, ""):
            warnings.append(f"变量 {{{{{name}}}}} 缺失，已渲染为空")
            return ""
        return str(value)

    return VARIABLE_RE.sub(_substitute, template or ""), warnings
