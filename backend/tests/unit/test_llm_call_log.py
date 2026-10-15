"""LLM 调用明细（llm_call）：适配器逐次尝试回调 / 记录器落库 / 任务层调用链。

覆盖：
- 适配器 on_attempt 契约（start/finish 事件；成功含输入/输出/usage/耗时；修复重试链；provider 错误）；
- CallRecorder：call_index / phase / attempt 组装与落库；进行中行（start 先落库、finish 原位更新）；
- 超时中断：超时行照常收口，被放弃线程的迟到结果不得二次落库；
- 启动对账：进程退出遗留的进行中行收口（close_stale_calls）；
- 任务层：AI 扩充与内容起草把"发给模型的输入 + 模型原始输出"写进 llm_call（含失败路径）。
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from saler.core.content import service as content_service
from saler.core.content.ai import run_content_draft
from saler.core.seeds import service as seed_service
from saler.core.seeds.ai import run_expansion
from saler.core.seeds.ai_translate import run_translate_seeds
from saler.db.models import LlmCall
from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.llm import call_log
from saler.providers.llm.openai_compatible import OpenAICompatibleProvider
from tests.fixtures.fakes.llm_fake import FakeLLMProvider

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "string"}}},
    "required": ["items"],
}


class _Usage:
    """pydantic 风格 usage 替身（走 model_dump 路径）。"""

    def __init__(self, **kw) -> None:
        self._kw = kw

    def model_dump(self) -> dict:
        return dict(self._kw)


class StubClient:
    """最小聊天桩：按脚本依次返回 (content, usage) 或抛出异常。"""

    def __init__(self, script: list) -> None:
        self.script = list(script)
        self.calls: list[dict] = []
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                item = outer.script.pop(0)
                if isinstance(item, Exception):
                    raise item
                content, usage = item if isinstance(item, tuple) else (item, None)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                    usage=usage,
                )

        self.chat = SimpleNamespace(completions=_Completions())


def _provider(script: list) -> OpenAICompatibleProvider:
    client = StubClient(script)
    return OpenAICompatibleProvider(
        base_url="http://stub",
        api_key="k",
        model="m",
        provider_name="stub",
        client_factory=lambda _t: client,
    )


# ---------- 适配器：on_attempt 契约 ----------


def _finishes(attempts: list[dict]) -> list[dict]:
    """一次尝试发两条事件：start（请求已发出，尚无结果）与 finish（本次尝试结束）。"""
    return [a for a in attempts if a.get("event") != "start"]


def test_attempt_events_bracket_the_request():
    provider = _provider([('{"items": ["ok"]}', None)])
    attempts: list[dict] = []
    provider.generate_structured(prompt="你好", schema=SCHEMA, on_attempt=attempts.append)
    assert [a["event"] for a in attempts] == ["start", "finish"]
    start, finish = attempts
    # start：请求已发出、结果未知（ok/latency/输出一律为空）——卡住时据此判断"发到哪一步"
    assert start["attempt"] == 1
    assert start["ok"] is None and start["latency_ms"] is None
    assert start["response_text"] is None and start["error_kind"] is None
    assert start["messages"][1]["content"] == "你好"
    assert finish["ok"] is True


def test_attempt_payload_carries_request_response_usage_latency():
    provider = _provider(
        [('{"items": ["ok"]}', _Usage(prompt_tokens=3, completion_tokens=5, total_tokens=8))]
    )
    attempts: list[dict] = []
    result = provider.generate_structured(prompt="你好", schema=SCHEMA, on_attempt=attempts.append)
    assert result == {"items": ["ok"]}
    (a,) = _finishes(attempts)
    assert a["attempt"] == 1
    assert a["ok"] is True and a["error_kind"] is None and a["error_detail"] is None
    assert a["provider"] == "stub" and a["model"] == "m"
    assert a["response_text"] == '{"items": ["ok"]}'
    assert a["usage"] == {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}
    assert isinstance(a["latency_ms"], int) and a["latency_ms"] >= 0
    # 记录的就是实际发送的消息（system 提示 + 用户输入）
    assert [m["role"] for m in a["messages"]] == ["system", "user"]
    assert a["messages"][1]["content"] == "你好"


def test_repair_chain_records_every_attempt_with_cumulative_messages():
    provider = _provider(["这不是 JSON", '{"items": ["ok"]}'])
    attempts: list[dict] = []
    provider.generate_structured(prompt="p", schema=SCHEMA, on_attempt=attempts.append)
    finishes = _finishes(attempts)
    assert [a["attempt"] for a in finishes] == [1, 2]
    first, second = finishes
    assert first["ok"] is False and first["error_kind"] == "invalid_output"
    assert first["response_text"] == "这不是 JSON"
    # 第二次请求 = 原始对话 + 上次原始输出 + 修复指令（完整修复链可见）
    assert [m["role"] for m in second["messages"]] == ["system", "user", "assistant", "user"]
    assert second["messages"][2]["content"] == "这不是 JSON"
    assert second["messages"][3]["content"].startswith("请仅返回严格 JSON")
    assert second["ok"] is True


def test_schema_mismatch_attempt_records_validation_detail():
    provider = _provider(['{"items": 123}', '{"items": ["ok"]}'])
    attempts: list[dict] = []
    provider.generate_structured(prompt="p", schema=SCHEMA, on_attempt=attempts.append)
    first = _finishes(attempts)[0]
    assert first["ok"] is False and first["error_kind"] == "invalid_output"
    assert "schema 校验失败" in first["error_detail"]
    assert first["response_text"] == '{"items": 123}'


def test_provider_error_attempt_recorded_before_raise():
    provider = _provider([RuntimeError("boom")])
    attempts: list[dict] = []
    with pytest.raises(ProviderError) as excinfo:
        provider.generate_structured(prompt="p", schema=SCHEMA, on_attempt=attempts.append)
    assert excinfo.value.kind == ErrorKind.NETWORK
    (a,) = _finishes(attempts)
    assert a["ok"] is False and a["error_kind"] == "network"
    assert a["response_text"] is None
    assert "boom" in (a["error_detail"] or "")


def test_broken_recorder_does_not_break_generation():
    provider = _provider(['{"items": ["ok"]}'])

    def _boom(_payload: dict) -> None:
        raise RuntimeError("recorder down")

    assert provider.generate_structured(prompt="p", schema=SCHEMA, on_attempt=_boom) == {"items": ["ok"]}


def test_translate_forwards_on_attempt():
    provider = _provider(['{"items": ["A", "B"]}'])
    attempts: list[dict] = []
    out = provider.translate(
        items=["甲", "乙"], source_lang="zh", target_lang="en", on_attempt=attempts.append
    )
    assert out == ["A", "B"]
    finishes = _finishes(attempts)
    assert len(finishes) == 1 and finishes[0]["ok"] is True


# ---------- 记录器：call_index / phase / 落库 ----------


def _payload(**over) -> dict:
    base = {
        "provider": "stub",
        "model": "m",
        "attempt": 1,
        "messages": [{"role": "user", "content": "hi"}],
        "response_text": '{"ok": true}',
        "ok": True,
        "error_kind": None,
        "error_detail": None,
        "latency_ms": 12,
        "usage": {"total_tokens": 3},
    }
    base.update(over)
    return base


def test_recorder_groups_attempts_into_calls_and_carries_phase(session_factory):
    recorder = call_log.make_call_recorder(session_factory, job_id=None, operation="content_translate")
    recorder(_payload())  # 第 1 次调用
    recorder.phase = "lang:ru"
    recorder(_payload())  # 第 2 次调用
    recorder(_payload(attempt=2, ok=False, error_kind="invalid_output"))  # 第 2 次调用的修复
    with session_factory() as db:
        rows = db.query(LlmCall).order_by(LlmCall.id).all()
    assert [r.call_index for r in rows] == [1, 2, 2]
    assert [r.attempt for r in rows] == [1, 1, 2]
    assert [r.phase for r in rows] == [None, "lang:ru", "lang:ru"]
    assert all(r.operation == "content_translate" and r.job_id is None for r in rows)
    assert rows[0].provider == "stub" and rows[0].model == "m"
    assert rows[0].request_messages == [{"role": "user", "content": "hi"}]
    assert rows[0].response_text == '{"ok": true}'
    assert rows[0].latency_ms == 12 and rows[0].usage == {"total_tokens": 3}
    assert rows[0].ts is not None
    assert rows[2].ok is False and rows[2].error_kind == "invalid_output"


def test_recorder_creates_running_row_and_finishes_it_in_place(session_factory):
    """start 先落一行"进行中"（ok=NULL）：请求已发出即可见；finish 原位收口，不新增行。"""
    recorder = call_log.make_call_recorder(session_factory, job_id=8, operation="seed_expand")
    recorder(_payload(event="start", ok=None, latency_ms=None, response_text=None))
    with session_factory() as db:
        (running,) = db.query(LlmCall).all()
    assert running.ok is None and running.latency_ms is None and running.response_text is None
    assert running.request_messages == [{"role": "user", "content": "hi"}]  # 卡住时也能看到入参
    running_id = running.id

    recorder(_payload())  # finish（同一次尝试）
    with session_factory() as db:
        rows = db.query(LlmCall).all()
    assert len(rows) == 1 and rows[0].id == running_id
    assert rows[0].ok is True and rows[0].latency_ms == 12
    assert rows[0].response_text == '{"ok": true}'


def test_recorder_start_events_advance_call_index_per_attempt_one(session_factory):
    recorder = call_log.make_call_recorder(session_factory, job_id=None, operation="seed_translate")
    recorder.phase = "lang:en"
    recorder(_payload(event="start", ok=None, latency_ms=None, response_text=None))
    recorder(_payload())  # 第 1 次调用完成
    recorder.phase = "lang:ru"
    recorder(_payload(event="start", ok=None, latency_ms=None, response_text=None))
    recorder(_payload(ok=False, error_kind="timeout", latency_ms=120_000))
    with session_factory() as db:
        rows = db.query(LlmCall).order_by(LlmCall.id).all()
    assert [(r.call_index, r.phase, r.ok) for r in rows] == [
        (1, "lang:en", True),
        (2, "lang:ru", False),
    ]


def test_close_stale_calls_closes_abandoned_running_rows(session_factory):
    """启动对账：进程退出遗留的"进行中"行收口为失败并留痕；已结束的行不动。"""
    with session_factory() as db:
        db.add(LlmCall(job_id=1, operation="seed_expand", ok=None))
        db.add(LlmCall(job_id=2, operation="seed_expand", ok=True, latency_ms=5))
        db.commit()
    with session_factory() as db:
        closed = call_log.close_stale_calls(db)
    assert closed == 1
    with session_factory() as db:
        rows = db.query(LlmCall).order_by(LlmCall.id).all()
    assert rows[0].ok is False and "中断" in (rows[0].error_detail or "")
    assert rows[1].ok is True and rows[1].error_detail is None


class _HangingClient:
    """create 挂起不返回；close 后立刻返回（模拟被放弃线程随后迟到返回）。"""

    def __init__(self, block_s: float) -> None:
        self.block_s = block_s
        self._release = threading.Event()
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer._release.wait(outer.block_s)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content='{"items": ["late"]}'))],
                    usage=None,
                )

        self.chat = SimpleNamespace(completions=_Completions())

    def close(self) -> None:
        self._release.set()


def test_timeout_finishes_running_row_and_discards_late_result(session_factory):
    """挂起超限：本次尝试以 timeout 收口（不残留"进行中"），迟到返回不得二次落库。"""
    client = _HangingClient(block_s=0.5)
    provider = OpenAICompatibleProvider(
        base_url="http://stub", api_key="k", model="m",
        provider_name="stub", client_factory=lambda _t: client,
    )
    recorder = call_log.make_call_recorder(session_factory, job_id=8, operation="seed_expand")
    with pytest.raises(ProviderError) as excinfo:
        provider.generate_structured(prompt="p", schema=SCHEMA, deadline_s=0.1, on_attempt=recorder)
    assert excinfo.value.kind == ErrorKind.TIMEOUT
    with session_factory() as db:
        (row,) = db.query(LlmCall).all()
    assert row.ok is False and row.error_kind == "timeout" and row.job_id == 8

    time.sleep(0.6)  # 等待被放弃的线程返回（迟到结果只能被丢弃）
    with session_factory() as db:
        rows = db.query(LlmCall).all()
    assert len(rows) == 1 and rows[0].ok is False and rows[0].error_kind == "timeout"


def test_prune_calls_removes_old_and_excess_rows(session_factory):
    from datetime import UTC, datetime, timedelta

    with session_factory() as db:
        now = datetime.now(UTC)
        db.add_all(
            [
                LlmCall(ts=now - timedelta(days=40), operation="seed_expand"),
                LlmCall(ts=now - timedelta(days=1), operation="seed_expand"),
                LlmCall(ts=now - timedelta(hours=1), operation="content_draft"),
            ]
        )
        db.commit()
    with session_factory() as db:
        removed = call_log.prune_calls(db, keep_days=30, keep_max=1)
        assert removed == 2  # 1 条超期 + 1 条超上限
        assert db.query(LlmCall).count() == 1
        assert db.query(LlmCall).one().operation == "content_draft"


# ---------- 任务层：调用链归属任务 ----------


class _Ctx:
    """JobContext 轻量替身（带 job_id，验证明细归属任务）。"""

    def __init__(self, job_id: int = 42) -> None:
        self.job_id = job_id
        self.progress_calls: list[dict] = []
        self.logs: list[str] = []

    def progress(self, **data) -> None:
        self.progress_calls.append(data)

    def log(self, message: str, **_kwargs) -> None:
        self.logs.append(message)

    async def checkpoint(self) -> None:
        return None


async def test_expansion_records_model_io_chain(session_factory):
    provider = FakeLLMProvider()
    await run_expansion(_Ctx(), session_factory, provider, payload={"description": "紧固件出口", "count": 3})
    with session_factory() as db:
        rows = db.query(LlmCall).order_by(LlmCall.id).all()
    assert len(rows) == 1
    row = rows[0]
    assert (row.job_id, row.operation, row.call_index, row.attempt, row.ok) == (
        42,
        "seed_expand",
        1,
        1,
        True,
    )
    assert row.provider == "fake" and row.model == "fake-model"
    user_text = "\n".join(m["content"] for m in row.request_messages if m["role"] == "user")
    assert "紧固件出口" in user_text  # 记录的就是发给模型的输入
    assert row.response_text  # 模型原始输出留档
    assert row.latency_ms is not None


async def test_expansion_failed_call_is_recorded_before_propagating(session_factory):
    provider = FakeLLMProvider(script=[ProviderError(ErrorKind.AUTH, "bad key")])
    with pytest.raises(ProviderError):
        await run_expansion(_Ctx(), session_factory, provider, payload={})
    with session_factory() as db:
        row = db.query(LlmCall).one()
    assert row.ok is False and row.error_kind == "auth" and row.job_id == 42


async def test_content_draft_records_model_io_chain(session_factory):
    with session_factory() as db:
        theme = content_service.create_theme(db, name="冷启动邮件", content_type="email")
    provider = FakeLLMProvider(script=[{"subject": "主题", "body_md": "正文 {{company_name}}"}])
    await run_content_draft(
        _Ctx(7),
        session_factory,
        provider,
        payload={"theme_id": theme.id, "brief": "对肯尼亚电力客户介绍电力金具"},
    )
    with session_factory() as db:
        row = db.query(LlmCall).one()
    assert (row.job_id, row.operation, row.ok) == (7, "content_draft", True)
    assert "肯尼亚" in row.request_messages[0]["content"]
    assert row.response_text is not None and "subject" in row.response_text


async def test_translate_records_one_call_per_language_with_phase(session_factory):
    with session_factory() as db:
        seed = seed_service.create_seed(db, query="电力金具 供应商", lang="zh")
    provider = FakeLLMProvider()
    await run_translate_seeds(
        _Ctx(9),
        session_factory,
        provider,
        payload={"seed_ids": [seed.id], "targets": ["en", "ru"]},
    )
    with session_factory() as db:
        rows = db.query(LlmCall).order_by(LlmCall.id).all()
    assert [(r.call_index, r.phase, r.operation, r.job_id) for r in rows] == [
        (1, "lang:en", "seed_translate", 9),
        (2, "lang:ru", "seed_translate", 9),
    ]
