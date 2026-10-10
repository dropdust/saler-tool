"""营销计划 API：CRUD / 预估 / 轮次 / 执行控制 / 台账 / 报表 / 试发（FR-046~053）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from saler.api.deps import get_session, paginate, pagination
from saler.api.errors import conflict, not_found
from saler.api.serializers import campaign_round_to_dict, campaign_to_dict, send_record_to_dict
from saler.core.campaigns import audience as audience_service
from saler.core.campaigns import estimate as estimate_service
from saler.core.campaigns import service as campaign_service
from saler.core.errors import ValidationFailed
from saler.core.sending import engine
from saler.db.models import Channel, Company, SendRecord
from saler.services import campaign_report

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class CampaignCreate(BaseModel):
    name: str
    content_theme_id: int
    channel_ids: list = Field(min_length=1)
    audience: dict = Field(default_factory=dict)
    lang_strategy: str = "auto"
    fixed_lang: str | None = None
    fallback_lang: str | None = None
    schedule: dict = Field(default_factory=dict)


class CampaignUpdate(BaseModel):
    name: str | None = None
    content_theme_id: int | None = None
    audience: dict | None = None
    lang_strategy: str | None = None
    fixed_lang: str | None = None
    fallback_lang: str | None = None
    schedule: dict | None = None


class RoundCreate(BaseModel):
    round_no: int | None = None
    content_theme_id: int | None = None
    interval_days: int | None = None
    condition: str = "no_reply_or_progress"


class TestSendRequest(BaseModel):
    n: int = 2
    to: str | None = None
    to_self: bool = False


class RetryRequest(BaseModel):
    record_ids: list[int] = Field(min_length=1)


def _detail(db: Session, campaign_id: int) -> dict:
    campaign = campaign_service.get_campaign(db, campaign_id)
    view = campaign_to_dict(campaign)
    view["rounds"] = [campaign_round_to_dict(row) for row in campaign_service.list_rounds(db, campaign_id)]
    view["channels"] = []
    for row in audience_service.channel_rows(db, campaign_id):
        channel = db.get(Channel, row.channel_id)
        view["channels"].append(
            {"channel_id": row.channel_id, "role": row.role,
             "name": channel.name if channel else None}
        )
    active = campaign_service.active_job(db, campaign_id)
    view["active_job_id"] = active.id if active else None
    return view


@router.get("")
def list_campaigns(
    status: str | None = None,
    db: Session = Depends(get_session),
) -> list[dict]:
    return [campaign_to_dict(row) for row in campaign_service.list_campaigns(db, status=status)]


@router.post("", status_code=201)
def create_campaign(payload: CampaignCreate, db: Session = Depends(get_session)) -> dict:
    campaign = campaign_service.create_campaign(db, **payload.model_dump())
    return _detail(db, campaign.id)


@router.get("/{campaign_id}")
def get_campaign(campaign_id: int, db: Session = Depends(get_session)) -> dict:
    return _detail(db, campaign_id)


@router.put("/{campaign_id}")
def update_campaign(
    campaign_id: int, payload: CampaignUpdate, db: Session = Depends(get_session)
) -> dict:
    campaign_service.update_campaign(db, campaign_id, **payload.model_dump(exclude_unset=True))
    return _detail(db, campaign_id)


@router.delete("/{campaign_id}")
def delete_campaign(campaign_id: int, db: Session = Depends(get_session)) -> dict:
    campaign_service.delete_campaign(db, campaign_id)
    return {"ok": True}


@router.post("/{campaign_id}/estimate")
def estimate_campaign(campaign_id: int, db: Session = Depends(get_session)) -> dict:
    campaign = campaign_service.get_campaign(db, campaign_id)
    return estimate_service.estimate(db, campaign)


# ---------- 轮次与执行 ----------


@router.get("/{campaign_id}/rounds")
def list_rounds(campaign_id: int, db: Session = Depends(get_session)) -> list[dict]:
    campaign_service.get_campaign(db, campaign_id)
    return [campaign_round_to_dict(row) for row in campaign_service.list_rounds(db, campaign_id)]


@router.post("/{campaign_id}/rounds", status_code=201)
def add_round(campaign_id: int, payload: RoundCreate, db: Session = Depends(get_session)) -> dict:
    row = campaign_service.add_round(db, campaign_id, **payload.model_dump())
    return campaign_round_to_dict(row)


async def _start_round(request: Request, db: Session, campaign_id: int, round_no: int) -> dict:
    campaign = campaign_service.get_campaign(db, campaign_id)
    if campaign_service.active_job(db, campaign_id) is not None:
        raise conflict("该计划已有执行中的任务")
    try:
        round_row = campaign_service.start_round(db, campaign, round_no=round_no)
    except ValidationFailed as err:
        raise conflict(str(err)) from err
    manager = request.app.state.job_manager
    job_id = manager.create(
        "campaign_send",
        name=f"发送计划：{campaign.name}（第 {round_no} 轮）",
        ref_type="campaign",
        ref_id=campaign_id,
        params={"round_no": round_no},
    )
    session_factory = request.app.state.session_factory
    manager.start(
        job_id,
        lambda ctx: engine.run_campaign_round(ctx, session_factory, campaign_id, round_no),
    )
    campaign_service.log_campaign_event(
        db, campaign, f"启动第 {round_no} 轮发送（任务 #{job_id}）"
    )
    return {"job_id": job_id, "round": round_row.round_no}


@router.post("/{campaign_id}/start")
async def start_campaign(campaign_id: int, request: Request, db: Session = Depends(get_session)) -> dict:
    """启动（默认第 1 轮；已完成轮次的计划可按轮次端点单独启动）。"""
    return await _start_round(request, db, campaign_id, 1)


@router.post("/{campaign_id}/rounds/{round_no}/start")
async def start_round(
    campaign_id: int, round_no: int, request: Request, db: Session = Depends(get_session)
) -> dict:
    return await _start_round(request, db, campaign_id, round_no)


@router.post("/{campaign_id}/pause")
def pause_campaign(campaign_id: int, request: Request, db: Session = Depends(get_session)) -> dict:
    campaign = campaign_service.get_campaign(db, campaign_id)
    campaign_service.pause_campaign(db, campaign)
    job = campaign_service.active_job(db, campaign_id)
    if job is not None:
        request.app.state.job_manager.pause(job.id)
    return _detail(db, campaign_id)


@router.post("/{campaign_id}/resume")
def resume_campaign(campaign_id: int, request: Request, db: Session = Depends(get_session)) -> dict:
    campaign = campaign_service.get_campaign(db, campaign_id)
    campaign_service.resume_campaign(db, campaign)
    job = campaign_service.active_job(db, campaign_id)
    if job is not None and job.status == "paused":
        request.app.state.job_manager.resume(job.id)
    return _detail(db, campaign_id)


@router.post("/{campaign_id}/cancel")
def cancel_campaign(campaign_id: int, request: Request, db: Session = Depends(get_session)) -> dict:
    campaign = campaign_service.get_campaign(db, campaign_id)
    job = campaign_service.active_job(db, campaign_id)
    if job is not None:
        request.app.state.job_manager.cancel(job.id)
    campaign_service.cancel_campaign(db, campaign)
    campaign_service.log_campaign_event(db, campaign, "计划已中止", level="warn")
    return _detail(db, campaign_id)


# ---------- 台账 / 重试 / 报表 / 试发 ----------


@router.get("/{campaign_id}/records")
def list_records(
    campaign_id: int,
    status: str | None = None,
    round_no: int | None = None,
    page_params: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_session),
) -> dict:
    campaign_service.get_campaign(db, campaign_id)
    page, page_size = page_params
    query = db.query(SendRecord).filter_by(campaign_id=campaign_id)
    if status:
        query = query.filter(SendRecord.status == status)
    if round_no is not None:
        query = query.filter(SendRecord.round_no == round_no)
    query = query.order_by(SendRecord.round_no.asc(), SendRecord.id.asc())
    result = paginate(query, page, page_size)
    company_names = {row.id: (row.name or f"#{row.id}") for row in db.query(Company).all()}
    channel_names = {row.id: row.name for row in db.query(Channel).all()}
    result["items"] = [
        send_record_to_dict(
            row,
            company_name=company_names.get(row.company_id),
            channel_name=channel_names.get(row.channel_id),
        )
        for row in result["items"]
    ]
    return result


@router.post("/{campaign_id}/records/retry")
async def retry_records(
    campaign_id: int, payload: RetryRequest, request: Request, db: Session = Depends(get_session)
) -> dict:
    campaign_service.get_campaign(db, campaign_id)
    rows = (
        db.query(SendRecord)
        .filter(SendRecord.campaign_id == campaign_id, SendRecord.id.in_(payload.record_ids))
        .all()
    )
    rounds = {row.round_no for row in rows} or {1}
    reset = campaign_service.retry_records(db, campaign_id, payload.record_ids)
    if reset == 0:
        return {"reset": 0, "job_id": None}
    round_no = min(rounds)
    manager = request.app.state.job_manager
    job_id = manager.create(
        "campaign_send",
        name=f"重试发送：{campaign_service.get_campaign(db, campaign_id).name}",
        ref_type="campaign",
        ref_id=campaign_id,
        params={"round_no": round_no, "retry": True},
    )
    session_factory = request.app.state.session_factory
    manager.start(
        job_id,
        lambda ctx: engine.run_campaign_round(ctx, session_factory, campaign_id, round_no),
    )
    return {"reset": reset, "job_id": job_id}


@router.get("/{campaign_id}/report")
def get_report(campaign_id: int, db: Session = Depends(get_session)) -> dict:
    campaign_service.get_campaign(db, campaign_id)
    return campaign_report.report(db, campaign_id)


@router.post("/{campaign_id}/report/export")
def export_report(campaign_id: int, request: Request, db: Session = Depends(get_session)) -> dict:
    campaign_service.get_campaign(db, campaign_id)
    data_dir = request.app.state.data_dir
    if data_dir is None:
        raise not_found("数据目录")
    path = campaign_report.export_xlsx(db, campaign_id, out_dir=data_dir / "exports")
    return {"ok": True, "path": str(path)}


@router.post("/{campaign_id}/test-send")
def test_send(
    campaign_id: int, payload: TestSendRequest, db: Session = Depends(get_session)
) -> dict:
    """试发（FR-053）：渲染真实内容发给自己，不写台账、不占额度。"""
    campaign = campaign_service.get_campaign(db, campaign_id)
    return engine.test_send(db, campaign, n=payload.n, to=payload.to, to_self=payload.to_self)
