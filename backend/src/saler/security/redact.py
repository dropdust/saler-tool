"""日志与导出的脱敏（FR-006 / 宪法第 V 条）。"""

from __future__ import annotations

import re
from typing import Any

SECRET_KEY_PATTERN = re.compile(
    r"(secret|password|passwd|token|api[-_]?key|auth[-_]?code|credential|authorization)",
    re.IGNORECASE,
)
MASK = "***"

# 已知明文密钥值的注册表：确保动态值不会经异常文本/日志泄露
_known_secret_values: set[str] = set()


def register_secret_value(value: str | None) -> None:
    """登记一个明文密钥值，其任何后续日志文本出现将被抹掉。"""
    if value and len(value) >= 6:
        _known_secret_values.add(value)


def scrub_text(text: str) -> str:
    for value in _known_secret_values:
        text = text.replace(value, MASK)
    return text


def redact(value: Any) -> Any:
    """递归脱敏：疑似密钥字段的值替换为 ***（用于结构化 payload/导出）。"""
    if isinstance(value, dict):
        return {
            k: (MASK if SECRET_KEY_PATTERN.search(str(k)) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


def install_log_redaction() -> None:
    """安装 loguru 全局脱敏补丁（启动时调用一次）。"""
    from loguru import logger

    def _patcher(record: dict) -> None:
        record["message"] = scrub_text(str(record["message"]))

    logger.configure(patcher=_patcher)
