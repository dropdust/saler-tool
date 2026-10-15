"""客户/线索 API：列表修订、联系方式管理、合并、导入导出（FR-027~029）。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from saler.api.deps import get_session, paginate, pagination
from saler.api.errors import conflict, not_found, unprocessable
from saler.api.serializers import company_to_dict, contact_to_dict
from saler.core.errors import Duplicate, ValidationFailed
from saler.core.errors import NotFound as DomainNotFound
from saler.core.leads import company_service
from saler.core.leads.extractor import normalize_email
from saler.db.models import Company, Contact
from saler.jobs.catalog import register_starter
from saler.services import export_leads
from saler.services.import_customers import run_import

router = APIRouter(prefix="/companies", tags=["companies"])


class CompanyUpdate(BaseModel):
    name: str | None = None
    country: str | None = None
    language: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    note: str | None = None
    is_excluded: bool | None = None
    exclusion_reason: str | None = None


class MergeRequest(BaseModel):
    target_id: int
    source_ids: list[int]


class ContactCreate(BaseModel):
    type: str
    value: str
    category: str = "general"
    source_url: str | None = None
    validity: str = "valid"


class ContactUpdate(BaseModel):
    category: str | None = None
    validity: str | None = None
    is_primary: bool | None = None


class ImportRequest(BaseModel):
    content: str | None = None
    path: str | None = None


class ExportRequest(BaseModel):
    format: Literal["csv", "xlsx"] = "csv"
    status: str | None = None
    country: str | None = None


def _company_view(db: Session, company: Company) -> dict:
    domain_row = company_service.primary_domain(db, company.id)
    count = db.query(Contact).filter_by(company_id=company.id).count()
    return company_to_dict(
        company, domain=domain_row.domain if domain_row else None, contacts_count=count
    )


def _get_company_or_404(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise not_found("客户公司")
    return company


def _get_contact_or_404(db: Session, contact_id: int) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise not_found("联系方式")
    return contact


@router.get("")
def list_companies(
    q: str | None = None,
    country: str | None = None,
    language: str | None = None,
    status: str | None = None,
    excluded: bool | None = Query(default=None),
    page_params: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_session),
) -> dict:
    page, page_size = page_params
    result = paginate(
        company_service.list_companies(
            db, q=q, country=country, language=language, status=status, excluded=excluded
        ),
        page,
        page_size,
    )
    result["items"] = [_company_view(db, row) for row in result["items"]]
    return result


@router.post("/merge")
def merge_companies(payload: MergeRequest, db: Session = Depends(get_session)) -> dict:
    return company_service.merge_companies(
        db, target_id=payload.target_id, source_ids=payload.source_ids
    )


def start_company_import_job(request: Request, *, params: dict) -> dict:
    """装配并启动一次客户名单导入——原发端点与重跑 starter 共用同一路径。"""
    manager = request.app.state.job_manager
    job_id = manager.create("company_import", name="导入客户名单", params=params)
    manager.start(
        job_id,
        lambda ctx: run_import(ctx, request.app.state.session_factory, payload=params),
    )
    return {"job_id": job_id}


def _rerun_company_import(request: Request, _db, job) -> dict:
    """重跑 starter（契约 §3）：以原任务 params 原样重建导入请求。"""
    return start_company_import_job(request, params=dict(job.params or {}))


register_starter("company_import", _rerun_company_import)


@router.post("/import", status_code=202)
async def import_companies(payload: ImportRequest, request: Request) -> dict:
    return start_company_import_job(request, params=payload.model_dump())


@router.post("/export")
def export_companies_endpoint(
    payload: ExportRequest, request: Request, db: Session = Depends(get_session)
) -> dict:
    data_dir = Path(request.app.state.data_dir or Path.cwd())
    return export_leads.export_companies(
        db,
        fmt=payload.format,
        out_dir=data_dir / "exports",
        status=payload.status,
        country=payload.country,
    )


@router.get("/{company_id}")
def get_company(company_id: int, db: Session = Depends(get_session)) -> dict:
    company = _get_company_or_404(db, company_id)
    view = _company_view(db, company)
    view["contacts"] = [
        contact_to_dict(row)
        for row in db.query(Contact)
        .filter_by(company_id=company.id)
        .order_by(Contact.type.asc(), Contact.id.asc())
        .all()
    ]
    return view


@router.put("/{company_id}")
def update_company(company_id: int, payload: CompanyUpdate, db: Session = Depends(get_session)) -> dict:
    fields = payload.model_dump(exclude_none=True)
    new_status = fields.pop("status", None)
    company = company_service.update_company(db, company_id, **fields)
    if new_status is not None and new_status != company.status:
        company = company_service.mark_status(db, company_id, new_status)  # FR-054 即时联动
    return _company_view(db, company)


@router.get("/{company_id}/contacts")
def list_contacts(company_id: int, db: Session = Depends(get_session)) -> list[dict]:
    _get_company_or_404(db, company_id)
    rows = (
        db.query(Contact)
        .filter_by(company_id=company_id)
        .order_by(Contact.type.asc(), Contact.id.asc())
        .all()
    )
    return [contact_to_dict(row) for row in rows]


@router.post("/{company_id}/contacts", status_code=201)
def add_contact(company_id: int, payload: ContactCreate, db: Session = Depends(get_session)) -> dict:
    _get_company_or_404(db, company_id)
    value_normalized = payload.value.strip()
    if payload.type == "email":
        normalized = normalize_email(payload.value)
        if normalized is None:
            raise unprocessable("邮箱格式无效（或属于应丢弃的噪声类型）")
        value_normalized = normalized
    elif payload.type in ("phone", "whatsapp"):
        digits = "".join(ch for ch in payload.value if ch.isdigit())
        if not (7 <= len(digits) <= 15):
            raise unprocessable("号码格式无效")
        value_normalized = digits
    try:
        contact, _created = company_service.upsert_contact(
            db,
            company_id=company_id,
            type_=payload.type,
            value=payload.value.strip(),
            value_normalized=value_normalized,
            category=payload.category,
            source_url=payload.source_url,
            validity=payload.validity,
        )
    except (Duplicate, ValidationFailed, DomainNotFound) as exc:  # pragma: no cover - 防御
        raise conflict(str(exc)) from exc
    return contact_to_dict(contact)


@router.put("/{company_id}/contacts/{contact_id}")
def update_contact(
    company_id: int, contact_id: int, payload: ContactUpdate, db: Session = Depends(get_session)
) -> dict:
    _get_company_or_404(db, company_id)
    contact = _get_contact_or_404(db, contact_id)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(contact, key, value)
    db.commit()
    return contact_to_dict(contact)


@router.delete("/{company_id}/contacts/{contact_id}")
def delete_contact(company_id: int, contact_id: int, db: Session = Depends(get_session)) -> dict:
    contact = _get_contact_or_404(db, contact_id)
    db.delete(contact)
    db.commit()
    return {"ok": True}
