"""备份与恢复 API（FR-004/SC-005；contracts/local-api.md）。

- POST /backups → job（生成归档并登记 BackupRecord）
- GET /backups、POST /backups/validate
- POST /restore → job：整库替换后释放旧连接、把本任务记录写回新库（恢复后仍可查询）
- POST /export/all → job（全量开放格式导出，未来 Web 版迁移预留）
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from saler import __version__
from saler.api.deps import get_session, paginate, pagination
from saler.api.serializers import iso
from saler.db.models import BackupRecord, Job
from saler.services import backup as backup_service

router = APIRouter(tags=["backup"])

JOB_FIELDS = (
    "id",
    "job_type",
    "name",
    "status",
    "params",
    "progress",
    "result",
    "error",
    "ref_type",
    "ref_id",
    "created_at",
    "started_at",
    "finished_at",
)


class BackupRequest(BaseModel):
    include_secrets: bool = False


class PathRequest(BaseModel):
    path: str


def _snapshot_job(session_factory: sessionmaker[Session], job_id: int) -> dict | None:
    with session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            return None
        return {field: getattr(job, field) for field in JOB_FIELDS}


def _reinject_job(session_factory: sessionmaker[Session], row: dict) -> None:
    """把任务记录写回（可能刚被替换的）数据库，供恢复后继续查询与收尾。"""
    with session_factory() as db:
        if db.get(Job, row["id"]) is None:
            payload = dict(row)
            payload["status"] = "running"
            payload["result"] = None
            db.add(Job(**payload))
            db.commit()


@router.post("/backups", status_code=202)
async def create_backup_endpoint(
    payload: BackupRequest, request: Request, db: Session = Depends(get_session)
) -> dict:
    data_dir = Path(request.app.state.data_dir or Path.cwd())
    manager = request.app.state.job_manager
    job_id = manager.create("backup", name="创建备份", params=payload.model_dump())

    async def run_job(ctx):
        result = await asyncio.to_thread(
            backup_service.create_backup, data_dir, include_secrets=payload.include_secrets
        )
        with request.app.state.session_factory() as session:
            session.add(
                BackupRecord(
                    path=result["path"],
                    kind="manual",
                    app_version=__version__,
                    schema_version=result["manifest"].get("schema_version"),
                    size_bytes=result["size_bytes"],
                    checksum=result["manifest"]["db_sha256"],
                )
            )
            session.commit()
        ctx.progress(phase="done")
        ctx.log(f"备份完成：{result['path']}")
        return result

    manager.start(job_id, run_job)
    return {"job_id": job_id}


@router.get("/backups")
def list_backups(
    page_params: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_session),
) -> dict:
    page, page_size = page_params
    result = paginate(db.query(BackupRecord).order_by(BackupRecord.id.desc()), page, page_size)
    result["items"] = [
        {
            "id": row.id,
            "path": row.path,
            "kind": row.kind,
            "size_bytes": row.size_bytes,
            "schema_version": row.schema_version,
            "created_at": iso(row.created_at),
        }
        for row in result["items"]
    ]
    return result


@router.post("/backups/validate")
def validate_backup(payload: PathRequest) -> dict:
    info = backup_service.validate_backup(payload.path)
    return {"ok": True, "manifest": info["manifest"]}


@router.post("/restore", status_code=202)
async def restore_endpoint(payload: PathRequest, request: Request) -> dict:
    data_dir = Path(request.app.state.data_dir or Path.cwd())
    manager = request.app.state.job_manager
    job_id = manager.create("restore", name="恢复备份", params=payload.model_dump())

    async def run_job(ctx):
        snapshot = _snapshot_job(request.app.state.session_factory, ctx.job_id)
        result = await asyncio.to_thread(backup_service.restore_backup, payload.path, data_dir)
        # 整库已被替换：释放旧连接池，并把本任务记录写回新库
        engine = request.app.state.engine
        if engine is not None:
            engine.dispose()
        if snapshot:
            _reinject_job(request.app.state.session_factory, snapshot)
        ctx.log("恢复完成：数据库已整体替换，旧库已留档（saler.db.pre-restore-*）")
        return result

    manager.start(job_id, run_job)
    return {"job_id": job_id}


@router.post("/export/all", status_code=202)
async def export_all_endpoint(request: Request) -> dict:
    data_dir = Path(request.app.state.data_dir or Path.cwd())
    manager = request.app.state.job_manager
    job_id = manager.create("export_all", name="全量导出")

    async def run_job(ctx):
        from saler.services.export_all import export_all_data  # T085

        result = await asyncio.to_thread(
            export_all_data, request.app.state.session_factory, data_dir
        )
        ctx.log(f"全量导出完成：{result['path']}")
        ctx.progress(phase="done")
        return result

    manager.start(job_id, run_job)
    return {"job_id": job_id}
