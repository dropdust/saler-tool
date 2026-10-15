"""真客户端（httpx + openai SDK）的调用硬时限：本机"收包不回"服务端（T271）。

桩客户端测不到的部分在此锁定：真实客户端的超时配置、主动断连能否唤醒被放弃的线程、
以及明细"进行中 → 超时收口"的整链（recorder 落库）。
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

from saler.db.models import LlmCall
from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.llm import call_log
from saler.providers.llm.openai_compatible import OpenAICompatibleProvider

SCHEMA = {"type": "object", "properties": {"items": {"type": "array"}}, "required": ["items"]}


def _hanging_server() -> tuple[str, socket.socket]:
    """本机服务端：收下连接与请求但永不回包（模拟网关/服务端卡死）。"""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    connections: list[socket.socket] = []

    def _serve() -> None:
        conn, _addr = server.accept()
        connections.append(conn)
        time.sleep(10)  # 不回包；客户端断连/进程结束时清理

    threading.Thread(target=_serve, daemon=True).start()
    return f"http://127.0.0.1:{server.getsockname()[1]}/v1", server


def test_real_client_aborts_hang_at_deadline_and_settles_running_row(session_factory):
    base_url, server = _hanging_server()
    try:
        provider = OpenAICompatibleProvider(
            base_url=base_url, api_key="k", model="m", provider_name="local-hang"
        )  # 不注入 client_factory：走真实 openai/httpx 传输
        recorder = call_log.make_call_recorder(session_factory, job_id=8, operation="seed_expand")

        started = time.monotonic()
        with pytest.raises(ProviderError) as excinfo:
            provider.generate_structured(
                prompt="p", schema=SCHEMA, deadline_s=0.5, on_attempt=recorder
            )
        elapsed = time.monotonic() - started
        assert excinfo.value.kind == ErrorKind.TIMEOUT
        assert elapsed < 5  # 不等服务端（它 10s 才放手）

        with session_factory() as db:
            (row,) = db.query(LlmCall).all()
        assert (row.job_id, row.call_index, row.attempt) == (8, 1, 1)
        assert row.ok is False and row.error_kind == "timeout"
        assert row.latency_ms is not None and row.request_messages  # 入参留档
    finally:
        server.close()


def test_running_row_visible_while_request_in_flight(session_factory):
    """卡住期间明细即可见（ok=NULL + 入参）："到底阻塞在哪一步"不必等任务结束。"""
    base_url, server = _hanging_server()
    try:
        provider = OpenAICompatibleProvider(
            base_url=base_url, api_key="k", model="m", provider_name="local-hang"
        )
        recorder = call_log.make_call_recorder(session_factory, job_id=8, operation="seed_expand")
        errors: list[Exception] = []

        def _call() -> None:
            try:
                provider.generate_structured(
                    prompt="业务描述：紧固件出口", schema=SCHEMA, deadline_s=1.5, on_attempt=recorder
                )
            except Exception as exc:  # noqa: BLE001 - 断言的失败路径在 join 之后检查
                errors.append(exc)

        worker = threading.Thread(target=_call)
        worker.start()
        rows: list[LlmCall] = []
        wait_until = time.monotonic() + 1.0
        while time.monotonic() < wait_until:  # 等"进行中"行出现（请求已发出、尚未返回）
            with session_factory() as db:
                rows = db.query(LlmCall).all()
            if rows and rows[0].ok is None:
                break
            time.sleep(0.02)
        assert rows and rows[0].ok is None and rows[0].latency_ms is None
        assert "紧固件出口" in rows[0].request_messages[-1]["content"]

        worker.join(10)
        assert len(errors) == 1 and getattr(errors[0], "kind", None) == ErrorKind.TIMEOUT
        with session_factory() as db:
            (row,) = db.query(LlmCall).all()
        assert row.ok is False and row.error_kind == "timeout"  # 同一行原位收口
    finally:
        server.close()
