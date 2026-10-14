"""T228 任务类型目录：全量声明 / 能力白名单 / 未知类型缺省 / 负载字段派生（契约 §4）。"""

from __future__ import annotations

import re
from pathlib import Path

from saler.api.serializers import job_to_dict
from saler.db.models import Job
from saler.jobs import catalog

EXPECTED_PAUSABLE = {
    "crawl",
    "campaign_send",
    "seed_discover",
    "ai_seed_expand",
    "ai_seed_translate",
    "ai_term_translate",
    "ai_content_draft",
    "ai_content_translate",
}
EXPECTED_RERUNNABLE = {"crawl", "ingest_harvest", "company_import"}


def test_catalog_declares_all_job_types_used_by_routes():
    """目录键与路由层 `manager.create("<type>"` 调用集合完全一致（防漂移）。"""
    routes_dir = Path(__file__).resolve().parents[2] / "src" / "saler" / "api" / "routes"
    used: set[str] = set()
    for path in routes_dir.glob("*.py"):
        used.update(re.findall(r'manager\.create\(\s*"([a-z_]+)"', path.read_text(encoding="utf-8")))
    assert used == set(catalog.JOB_TYPES)
    assert len(catalog.JOB_TYPES) == 15


def test_pausable_whitelist():
    actual = {key for key, meta in catalog.JOB_TYPES.items() if meta.pausable}
    assert actual == EXPECTED_PAUSABLE


def test_rerunnable_declared_set():
    actual = {key for key, meta in catalog.JOB_TYPES.items() if meta.rerunnable}
    assert actual == EXPECTED_RERUNNABLE


def test_meta_default_for_unknown_type():
    for job_type in ("nope", None, ""):
        meta = catalog.meta(job_type)
        assert meta.pausable is False
        assert meta.rerunnable is False
    assert catalog.get_starter("nope") is None


def test_starter_registry_roundtrip():
    def _starter(request, db, original):  # noqa: ANN001, ARG001
        return {"job_id": 1}

    catalog.register_starter("crawl", _starter)
    try:
        assert catalog.get_starter("crawl") is _starter
    finally:
        catalog._RERUN_STARTERS.pop("crawl", None)
    assert catalog.get_starter("crawl") is None


def test_job_to_dict_derives_capabilities():
    crawl = job_to_dict(Job(job_type="crawl", name="挖掘"))
    assert crawl["can_pause"] is True
    assert crawl["rerunnable"] is True

    backup = job_to_dict(Job(job_type="backup", name="备份"))
    assert backup["can_pause"] is False
    assert backup["rerunnable"] is False

    unknown = job_to_dict(Job(job_type="mystery", name="?"))
    assert unknown["can_pause"] is False
    assert unknown["rerunnable"] is False
