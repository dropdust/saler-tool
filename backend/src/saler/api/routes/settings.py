"""应用设置 API（KV；未知键拒绝）+ 数据目录管理 + 操作日志查询。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from saler.api.deps import get_session
from saler.api.errors import bad_request
from saler.api.serializers import log_to_dict
from saler.services import operation_log, settings_service
from saler.services.datadir import check_writable, move_data_dir, resolve_data_dir

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings(db: Session = Depends(get_session)) -> dict:
    return settings_service.get_all(db)


class SettingsUpdate(BaseModel):
    values: dict


@router.put("")
def put_settings(payload: SettingsUpdate, db: Session = Depends(get_session)) -> dict:
    for key, value in payload.values.items():
        # 006 守卫：提示词模板键有专用域校验（/ai/prompts），通用端点一律拒绝——
        # 必须先于 is_known_key（行存在后 is_known_key 会放行，允许写脏形状）。
        # 前缀取 "prompt_template"（不带尾下划线）：单份键 prompt_template_* 与
        # 模板库键 prompt_templates_*（复数）都命中
        if key.startswith("prompt_template"):
            raise bad_request("提示词模板请通过 AI 提示词接口维护（/ai/prompts），避免绕过域校验")
        if not settings_service.is_known_key(db, key):
            raise bad_request(f"未知设置项：{key}")
        message = settings_service.value_error(key, value)
        if message is not None:
            raise bad_request(message)
        settings_service.set_value(db, key, value)
    return settings_service.get_all(db)


# ---------- 数据目录（FR-033） ----------


class DataDirRequest(BaseModel):
    path: str


def _current_data_dir(request: Request) -> Path:
    return Path(request.app.state.data_dir or resolve_data_dir())


@router.get("/data-dir")
def get_data_dir(request: Request) -> dict:
    current = _current_data_dir(request)
    ok, message = check_writable(current)
    return {"data_dir": str(current), "writable": ok, "message": message}


@router.post("/data-dir/validate")
def validate_data_dir(payload: DataDirRequest) -> dict:
    ok, message = check_writable(payload.path)
    return {"ok": ok, "message": message}


@router.post("/data-dir/move", status_code=202)
async def move_data_dir_endpoint(payload: DataDirRequest, request: Request) -> dict:
    current = _current_data_dir(request)
    manager = request.app.state.job_manager
    job_id = manager.create(
        "data_dir_move", name="迁移数据目录", params={"from": str(current), "to": payload.path}
    )

    async def run_job(ctx):
        result = await asyncio.to_thread(move_data_dir, current, payload.path)
        ctx.log("迁移完成：核对一致，重启应用后生效（旧数据保留在原位置）")
        ctx.progress(phase="done")
        return result

    manager.start(job_id, run_job)
    return {"job_id": job_id}


# ---------- 操作日志（FR-026，顶层路径 /logs） ----------

logs_router = APIRouter(tags=["logs"])


@logs_router.get("/logs")
def get_logs(
    ref_type: str | None = None,
    ref_id: int | None = None,
    level: str | None = None,
    job_type: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_session),
) -> list[dict]:
    entries = operation_log.query_logs(
        db, ref_type=ref_type, ref_id=ref_id, level=level, job_type=job_type, limit=limit
    )
    return [log_to_dict(entry) for entry in entries]
