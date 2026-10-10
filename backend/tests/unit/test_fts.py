"""T132 单元测试：FTS5 影子表——触发器同步/前缀匹配/回退与启用门槛。"""

from __future__ import annotations

import pytest

from saler.db import fts
from saler.db.models import Company, Contact

pytestmark = pytest.mark.skipif(
    not fts.fts5_supported(__import__("sqlalchemy").create_engine("sqlite://")),
    reason="本机 SQLite 未编译 FTS5",
)


def _company(db, name, *, email=None) -> Company:
    company = Company(name=name, source="crawl")
    db.add(company)
    db.commit()
    if email:
        db.add(
            Contact(
                company_id=company.id, type="email", value=email,
                value_normalized=email.lower(), is_primary=True,
            )
        )
        db.commit()
    return company


class TestShadow:
    def test_triggers_keep_index_in_sync(self, db, engine):
        assert fts.ensure_shadow(engine) is True
        company = _company(db, "Kenya Power Hardware Ltd", email="info@kpower.co.ke")
        assert fts.search_company_ids(engine, "hardware") == [company.id]

        _company(db, "Nairobi Cables Co")
        assert set(fts.search_company_ids(engine, "cables")) >= {
            row.id for row in db.query(Company).all() if "Cables" in (row.name or "")
        }

        # 更新与删除经触发器同步
        company.name = "Kenya Power Hardware Group"
        db.commit()
        assert fts.search_company_ids(engine, "group") == [company.id]
        db.query(Contact).filter_by(company_id=company.id).delete()
        db.delete(company)
        db.commit()
        assert fts.search_company_ids(engine, "group") == []

    def test_search_is_prefix_based_and_escapes_syntax(self, db, engine):
        fts.ensure_shadow(engine)
        company = _company(db, "Switchgear Trading Ltd")
        assert fts.search_company_ids(engine, "switch") == [company.id]
        assert fts.search_company_ids(engine, 'switch*(("') == [company.id]  # FTS 语法字符被清洗
        assert fts.search_company_ids(engine, "!@#$%") == []

    def test_contact_index(self, db, engine):
        fts.ensure_shadow(engine)
        company = _company(db, "Contactor Co", email="sales@contactor.example")
        contact_id = db.query(Contact).filter_by(company_id=company.id).one().id
        assert fts.search_contact_ids(engine, "contactor") == [contact_id]
        assert fts.search_contact_ids(engine, "sales@contactor") == [contact_id]

    def test_rebuild_restores_missing_rows(self, db, engine):
        fts.ensure_shadow(engine)
        company = _company(db, "Rebuild Target Inc")
        # 模拟影子表漂移（删掉索引内容）→ rebuild 恢复
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("INSERT INTO company_fts(company_fts) VALUES('delete-all')"))
            conn.commit()
        assert fts.search_company_ids(engine, "rebuild") == []
        fts.rebuild(engine)
        assert fts.search_company_ids(engine, "rebuild") == [company.id]


class TestGating:
    def test_setting_overrides_row_threshold(self, db, engine):
        from saler.services import settings_service

        _company(db, "Small Co")
        # 默认：规模不足 → 不用 FTS
        assert fts.should_use_fts(db) is False
        # 显式开启 → 使用
        settings_service.set_value(db, "search_fts", True)
        assert fts.should_use_fts(db) is True
        settings_service.set_value(db, "search_fts", False)
        assert fts.should_use_fts(db) is False

    def test_row_threshold_auto_enables(self, db, engine):
        for index in range(5):
            _company(db, f"Bulk {index}")
        assert fts.should_use_fts(db, min_rows=3) is True

    def test_company_search_uses_fts_when_enabled(self, client, db, engine):
        from saler.services import settings_service

        fts.ensure_shadow(engine)
        settings_service.set_value(db, "search_fts", True)
        _company(db, "FtsEnabled Kenya Ltd")
        _company(db, "Other Corp")
        resp = client.get("/api/v1/companies", params={"q": "ftsEnabled"})
        assert resp.status_code == 200, resp.text
        names = [row["name"] for row in resp.json()["items"]]
        assert names == ["FtsEnabled Kenya Ltd"]
