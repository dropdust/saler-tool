"""T012 安全基座测试：钥匙串回退 / 加解密往返 / 脱敏不泄露 / 启动令牌。"""

from __future__ import annotations

from saler.security.crypto import SecretBox
from saler.security.redact import MASK, redact, register_secret_value, scrub_text
from saler.security.token import AppToken


def test_encrypt_decrypt_roundtrip():
    box = SecretBox.generate()
    token = box.encrypt("smtp-授权码-123")
    assert isinstance(token, bytes)
    assert box.decrypt(token) == "smtp-授权码-123"


def test_passphrase_derivation_stable():
    box1 = SecretBox.from_passphrase("pw", salt=b"0123456789abcdef")
    box2 = SecretBox.from_passphrase("pw", salt=b"0123456789abcdef")
    assert box2.decrypt(box1.encrypt("x")) == "x"


def test_resolve_falls_back_to_key_file(tmp_path, monkeypatch):
    """钥匙串不可用 → 回退 0600 密钥文件；重复解析保持同一密钥。"""
    monkeypatch.delenv("SALER_MASTER_PASSPHRASE", raising=False)
    import saler.security.crypto as crypto

    monkeypatch.setattr(crypto, "_keyring_backend", lambda: None)

    box1 = crypto.resolve_secret_box(tmp_path)
    key_file = tmp_path / "secrets" / "master.key"
    assert key_file.exists()
    assert (key_file.stat().st_mode & 0o777) == 0o600

    box2 = crypto.resolve_secret_box(tmp_path)
    assert box2.decrypt(box1.encrypt("abc")) == "abc"


def test_resolve_passphrase_env_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("SALER_MASTER_PASSPHRASE", "pw123")
    import saler.security.crypto as crypto

    box1 = crypto.resolve_secret_box(tmp_path)
    box2 = crypto.resolve_secret_box(tmp_path)  # 同一 salt → 稳定
    assert box2.decrypt(box1.encrypt("kw")) == "kw"


def test_redact_structured_payload():
    data = {
        "api_key": "sk-1",
        "nested": {"password": "p", "ok": "keep"},
        "name": "公司A",
        "list": [{"token": "t"}],
    }
    out = redact(data)
    assert out["api_key"] == MASK
    assert out["nested"]["password"] == MASK
    assert out["nested"]["ok"] == "keep"
    assert out["name"] == "公司A"
    assert out["list"][0]["token"] == MASK


def test_scrub_text_removes_registered_values():
    register_secret_value("super-secret-token-1")
    scrubbed = scrub_text("error: super-secret-token-1 rejected")
    assert "super-secret-token-1" not in scrubbed
    assert MASK in scrubbed


def test_app_token_check():
    token = AppToken()
    assert token.check(token.value)
    assert not token.check("wrong")
    assert not token.check(None)
