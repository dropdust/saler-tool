"""主密钥与字段加密（Fernet）。

解析顺序（`resolve_secret_box`）：
1. 环境变量 ``SALER_MASTER_PASSPHRASE``（Argon2id 派生；无钥匙串的环境/自动化）；
2. OS 钥匙串（Windows Credential Manager / macOS Keychain / Linux Secret Service）；
3. 数据目录内 0600 权限的随机密钥文件 ``secrets/master.key``（最后兜底，日志告警）。

所有凭证字段经 `security/fields.EncryptedText` 加密落库；明文仅在内存中短暂存在。
"""

from __future__ import annotations

import base64
import os
import secrets as _secrets
from pathlib import Path

from cryptography.fernet import Fernet
from loguru import logger

SERVICE_NAME = "saler-tool"
_KEYRING_ENTRY = "master-key"
_PASSPHRASE_ENV = "SALER_MASTER_PASSPHRASE"


class SecretBox:
    """对敏感文本做 Fernet 加解密。"""

    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @classmethod
    def generate(cls) -> SecretBox:
        return cls(Fernet.generate_key())

    @classmethod
    def from_passphrase(cls, passphrase: str, *, salt: bytes) -> SecretBox:
        from argon2.low_level import Type, hash_secret_raw

        key = hash_secret_raw(
            passphrase.encode("utf-8"),
            salt,
            time_cost=3,
            memory_cost=65536,
            parallelism=2,
            hash_len=32,
            type=Type.ID,
        )
        return cls(base64.urlsafe_b64encode(key))

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, token: bytes) -> str:
        return self._fernet.decrypt(bytes(token)).decode("utf-8")


# ---------- 进程级注册表（应用启动或测试夹具注入） ----------

_box: SecretBox | None = None


def set_secret_box(box: SecretBox) -> None:
    global _box
    _box = box


def get_secret_box() -> SecretBox:
    if _box is None:
        raise RuntimeError("SecretBox 未初始化：应用启动时须调用 resolve_secret_box() 或 set_secret_box()")
    return _box


def _keyring_backend():
    """返回 keyring 模块；不可导入时返回 None（便于测试注入）。"""
    try:
        import keyring

        return keyring
    except Exception:
        return None


def resolve_secret_box(data_dir: Path | str) -> SecretBox:
    """按 口令环境变量 → OS 钥匙串 → 0600 密钥文件 的顺序解析主密钥。"""
    data_dir = Path(data_dir)
    secrets_dir = data_dir / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)

    # 1) 口令（环境变量）
    passphrase = os.environ.get(_PASSPHRASE_ENV)
    if passphrase:
        salt_file = secrets_dir / "passphrase.salt"
        if not salt_file.exists():
            salt_file.write_bytes(_secrets.token_bytes(16))
            os.chmod(salt_file, 0o600)
        box = SecretBox.from_passphrase(passphrase, salt=salt_file.read_bytes())
        set_secret_box(box)
        return box

    # 2) OS 钥匙串
    keyring = _keyring_backend()
    if keyring is not None:
        try:
            stored = keyring.get_password(SERVICE_NAME, _KEYRING_ENTRY)
            if stored:
                box = SecretBox(stored.encode("utf-8"))
            else:
                key = Fernet.generate_key()
                keyring.set_password(SERVICE_NAME, _KEYRING_ENTRY, key.decode("utf-8"))
                box = SecretBox(key)
            set_secret_box(box)
            return box
        except Exception as exc:  # 无钥匙串服务（如部分 Linux 桌面）→ 兜底
            logger.debug(f"keyring 不可用，回退本地密钥文件：{exc}")

    # 3) 0600 密钥文件（兜底）
    key_file = secrets_dir / "master.key"
    if key_file.exists():
        box = SecretBox(key_file.read_bytes().strip())
    else:
        key = Fernet.generate_key()
        key_file.write_bytes(key)
        os.chmod(key_file, 0o600)
        box = SecretBox(key)
    logger.warning("系统钥匙串不可用，主密钥保存在数据目录 secrets/master.key（0600）")
    set_secret_box(box)
    return box
