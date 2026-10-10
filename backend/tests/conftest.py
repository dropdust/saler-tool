"""测试共用夹具。

- `data_dir`：隔离的数据目录（每个测试独立）。
- `engine`/`db`：内存程度最低的临时 SQLite（WAL）+ 全部表结构。
- `client`：带启动令牌的 FastAPI 测试客户端（依赖 api.main.create_app）。
- `_secret_box`：自动注入的测试主密钥（不触碰系统钥匙串/文件）。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from saler.security.crypto import SecretBox, set_secret_box


@pytest.fixture(autouse=True)
def _secret_box():
    set_secret_box(SecretBox.generate())


@pytest.fixture()
def data_dir(tmp_path):
    d = tmp_path / "saler-data"
    d.mkdir()
    return d


@pytest.fixture()
def engine(tmp_path):
    import saler.db.models  # noqa: F401
    from saler.db.base import Base
    from saler.db.session import apply_sqlite_pragmas

    eng = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    apply_sqlite_pragmas(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def db(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture()
def client(engine, session_factory, data_dir):
    from fastapi.testclient import TestClient

    from saler.api.main import create_app

    app = create_app(
        engine=engine, session_factory=session_factory, token="test-token", data_dir=data_dir
    )
    with TestClient(app, headers={"X-App-Token": "test-token"}) as c:
        yield c


def wait_job(client, job_id: int, timeout: float = 10.0) -> dict:
    """轮询任务直至终态（测试助手）。"""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/v1/jobs/{job_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data["status"] in ("completed", "failed", "cancelled"):
            return data
        time.sleep(0.05)
    raise AssertionError(f"任务 {job_id} 超时未完成")
