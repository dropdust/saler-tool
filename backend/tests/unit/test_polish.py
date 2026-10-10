"""Phase 9 横切单测：代理回环绕过（T135）/ 维护任务（T136）/ AI 遥测（T137）/ 启动诊断（T134）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from saler.db.models import BackupRecord, OperationLog
from saler.jobs.maintenance import BACKUP_REMIND_DAYS, backup_due, run_maintenance
from saler.providers.llm import telemetry
from saler.services.operation_log import log_op


class TestProxyBypass:
    def test_merges_loopback_into_existing_value(self):
        from saler.services.proxy import apply_loopback_bypass, loopback_bypass_value

        assert loopback_bypass_value("example.com,127.0.0.1") == "example.com,127.0.0.1,localhost,::1"
        env: dict[str, str] = {"NO_PROXY": "corp.internal"}
        value = apply_loopback_bypass(env)
        assert value == "corp.internal,127.0.0.1,localhost,::1"
        assert env["no_proxy"] == value  # 大小写两种变量都设置

    def test_idempotent(self):
        from saler.services.proxy import apply_loopback_bypass

        env: dict[str, str] = {}
        first = apply_loopback_bypass(env)
        assert apply_loopback_bypass(env) == first


class TestMaintenance:
    def test_prunes_old_logs_and_reminds_backup(self, db):
        old = log_op(db, "system", "旧日志")
        old.ts = datetime.now(UTC) - timedelta(days=60)
        db.commit()
        log_op(db, "system", "新日志")

        result = run_maintenance(db, keep_days=30, keep_max=100_000)
        assert result["logs_removed"] == 1
        assert result["backup_due"] is True  # 从未备份 → 提醒
        messages = [row.message for row in db.query(OperationLog).all()]
        assert any("备份提醒" in message for message in messages)
        assert db.query(OperationLog).filter(OperationLog.message == "旧日志").count() == 0

    def test_backup_due_false_after_recent_backup(self, db):
        db.add(BackupRecord(path="/tmp/b.zip", kind="manual", size_bytes=1, checksum="x"))
        db.commit()
        assert backup_due(db, days=BACKUP_REMIND_DAYS) is False
        row = db.query(BackupRecord).one()
        row.created_at = datetime.now(UTC) - timedelta(days=BACKUP_REMIND_DAYS + 1)
        db.commit()
        assert backup_due(db, days=BACKUP_REMIND_DAYS) is True


class _StubProvider:
    provider_name = "stub-llm"
    model = "stub-model"

    def __init__(self, stats: dict | None) -> None:
        self.last_stats = stats


class TestTelemetry:
    def test_records_stats_to_operation_log(self, db):
        provider = _StubProvider({"attempts": 2, "repair_attempts": 1, "ok": True, "error_kind": None})
        payload = telemetry.record_from_provider(db, provider, operation="seed_expand")
        assert payload and payload["repair_attempts"] == 1
        row = db.query(OperationLog).order_by(OperationLog.id.desc()).first()
        assert row.job_type == "llm"
        assert "stub-llm/stub-model" in row.message and "修复 1 次" in row.message

    def test_skips_when_no_stats(self, db):
        assert telemetry.record_from_provider(db, _StubProvider(None), operation="x") is None
        assert db.query(OperationLog).count() == 0

    def test_snapshot_aggregates_retry_and_failure_rates(self, db):
        telemetry.record_from_provider(
            db, _StubProvider({"attempts": 1, "repair_attempts": 0, "ok": True, "error_kind": None}),
            operation="seed_expand",
        )
        telemetry.record_from_provider(
            db, _StubProvider({"attempts": 3, "repair_attempts": 2, "ok": False, "error_kind": "invalid_output"}),
            operation="seed_expand",
        )
        snapshot = telemetry.snapshot(db)
        assert len(snapshot) == 1
        assert snapshot[0]["calls"] == 2
        assert snapshot[0]["retried_calls"] == 1
        assert snapshot[0]["failed_calls"] == 1
        assert snapshot[0]["retry_rate"] == 0.5


class TestAdapterStats:
    def test_generate_structured_tracks_stats(self):
        from saler.providers.llm.openai_compatible import OpenAICompatibleProvider
        from tests.unit.test_llm_adapter import SCHEMA, _provider

        provider, _client = _provider(["这不是 JSON", '{"items": ["ok"]}'])
        assert isinstance(provider, OpenAICompatibleProvider)
        provider.generate_structured(prompt="p", schema=SCHEMA)
        assert provider.last_stats == {"attempts": 2, "repair_attempts": 1, "ok": True, "error_kind": None}


class TestDiagnostics:
    def test_check_environment_reports_supported_platform(self):
        from saler.desktop.diagnostics import check_desktop_environment

        diagnosis = check_desktop_environment()
        # 本机（Linux CI/开发机）应给出明确结论而非异常
        assert isinstance(diagnosis.ok, bool)
        assert diagnosis.detail

    def test_friendly_error_includes_hint_for_webkit(self):
        from saler.desktop.diagnostics import friendly_startup_error

        message = friendly_startup_error(RuntimeError("Failed to load web view: GLib.GError"))
        assert "WebKitGTK" in message or "webkit" in message.lower()
