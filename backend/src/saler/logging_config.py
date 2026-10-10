"""loguru 日志：控制台 + 数据目录滚动文件（自动脱敏）。"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from saler.security.redact import install_log_redaction


def setup_logging(data_dir: Path | str, *, level: str = "INFO") -> None:
    logs_dir = Path(data_dir) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(sys.stderr, level=level)
    logger.add(
        logs_dir / "saler.log",
        level=level,
        rotation="10 MB",
        retention=10,
        encoding="utf-8",
        enqueue=True,
    )
    install_log_redaction()
