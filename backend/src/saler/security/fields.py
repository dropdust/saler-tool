"""加密列类型：敏感文本以 Fernet 密文入库（宪法第 V 条）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator

from saler.security.crypto import get_secret_box


class EncryptedText(TypeDecorator[str]):
    """Fernet 加密的文本列。

    - 写入：密文（BYTEA）落库；
    - 读取：需进程内已初始化 SecretBox（应用启动或测试夹具负责）。
    - 任何接口层不得把解密结果序列化输出（服务层遵循"只写不读回"约定）。
    """

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> bytes | None:
        if value is None:
            return None
        return get_secret_box().encrypt(str(value))

    def process_result_value(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return get_secret_box().decrypt(value)
