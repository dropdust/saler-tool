"""契约：GET /ai/calls —— LLM 调用明细查询（按任务/操作过滤，倒序）。

用途：分析 AI 扩充/起草的一次任务里，模型收到了什么、返回了什么、修复了几次。
"""

from __future__ import annotations


def _payload(**over) -> dict:
    base = {
        "provider": "DeepSeek",
        "model": "deepseek-chat",
        "attempt": 1,
        "messages": [
            {"role": "system", "content": "你只输出严格 JSON"},
            {"role": "user", "content": "业务描述：紧固件出口"},
        ],
        "response_text": '{"nodes": []}',
        "ok": True,
        "error_kind": None,
        "error_detail": None,
        "latency_ms": 830,
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }
    base.update(over)
    return base


def test_ai_calls_lists_attempts_newest_first(client, session_factory):
    from saler.providers.llm.call_log import make_call_recorder

    expand = make_call_recorder(session_factory, job_id=None, operation="seed_expand")
    expand(_payload())
    expand(_payload(attempt=2, ok=False, error_kind="invalid_output", response_text="不是 JSON"))
    draft = make_call_recorder(session_factory, job_id=None, operation="content_draft")
    draft.phase = "draft"
    draft(_payload(response_text='{"subject": "hi"}'))

    resp = client.get("/api/v1/ai/calls")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 3
    items = data["items"]
    assert [item["operation"] for item in items] == ["content_draft", "seed_expand", "seed_expand"]
    first = items[1]
    assert first["attempt"] == 2 and first["ok"] is False
    assert first["error_kind"] == "invalid_output" and first["response_text"] == "不是 JSON"
    last = items[0]
    assert last["phase"] == "draft"
    assert last["request_messages"][1]["content"].startswith("业务描述")
    assert last["usage"]["total_tokens"] == 150
    assert last["latency_ms"] == 830
    assert last["job_id"] is None and last["call_index"] == 1
    assert last["ts"] is not None and last["provider"] == "DeepSeek"


def test_ai_calls_filters_by_operation_and_job(client, session_factory):
    from saler.providers.llm.call_log import make_call_recorder

    make_call_recorder(session_factory, job_id=5, operation="seed_expand")(_payload())
    make_call_recorder(session_factory, job_id=None, operation="content_draft")(_payload())

    resp = client.get("/api/v1/ai/calls", params={"operation": "seed_expand"})
    data = resp.json()
    assert data["total"] == 1 and data["items"][0]["job_id"] == 5

    resp = client.get("/api/v1/ai/calls", params={"job_id": 5})
    data = resp.json()
    assert data["total"] == 1 and data["items"][0]["operation"] == "seed_expand"

    resp = client.get("/api/v1/ai/calls", params={"job_id": 404})
    assert resp.json() == {"total": 0, "items": []}
