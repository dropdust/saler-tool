"""任务类型目录与重跑注册表——任务能力的单一事实源（契约 §3/§4，data-model.md §3/§4）。

- `JOB_TYPES`：全量任务类型的静态元数据（`pausable`/`rerunnable`）；`job_to_dict` 由本目录
  派生 `can_pause`/`rerunnable` 两字段，前端控制按钮据此渲染。
- `pausable` 与各引擎协作点（``ctx.checkpoint()``）实况一一对应（crawl/campaign_send/
  seed_discover/ai_*）；不具备协作点的短任务只提供取消——前端不亮暂停按钮，杜绝
  "显示已暂停、实际仍在跑"的谎报。
- `rerunnable` 与重跑 starter 注册表一致（目录测试断言防漂移）：starter 由各域路由模块
  在 import 时注册（registry 惯用法，同 providers）——新增可重跑类型 = 注册一行。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import Request
    from sqlalchemy.orm import Session

    from saler.db.models import Job

#: 重跑 starter 签名：(request, db, 原任务行) -> {job_id, ...}（crawl 附 crawl_job_id）
RerunStarter = Callable[["Request", "Session", "Job"], dict[str, Any]]


@dataclass(frozen=True)
class JobTypeMeta:
    pausable: bool = False  # 支持暂停/恢复（引擎含协作点）
    rerunnable: bool = False  # 可重新运行（断点安全语义，见 data-model.md §3 依据列）


JOB_TYPES: dict[str, JobTypeMeta] = {
    "crawl": JobTypeMeta(pausable=True, rerunnable=True),
    "campaign_send": JobTypeMeta(pausable=True),
    "seed_discover": JobTypeMeta(pausable=True),
    "ai_seed_expand": JobTypeMeta(pausable=True),
    "ai_seed_translate": JobTypeMeta(pausable=True),
    "ai_term_translate": JobTypeMeta(pausable=True),
    "ai_content_draft": JobTypeMeta(pausable=True),
    "ai_content_translate": JobTypeMeta(pausable=True),
    "ingest_harvest": JobTypeMeta(rerunnable=True),
    "company_import": JobTypeMeta(rerunnable=True),
    "seed_validate": JobTypeMeta(),
    "backup": JobTypeMeta(),
    "restore": JobTypeMeta(),
    "export_all": JobTypeMeta(),
    "data_dir_move": JobTypeMeta(),
}

_RERUN_STARTERS: dict[str, RerunStarter] = {}


def meta(job_type: str | None) -> JobTypeMeta:
    """任务类型元数据；未知/空类型返回全缺省（不可暂停、不可重跑）。"""
    return JOB_TYPES.get(job_type or "", JobTypeMeta())


def register_starter(job_type: str, starter: RerunStarter) -> None:
    """注册某类型的重跑 starter（域路由模块 import 时调用；重复注册以最后一次为准）。"""
    _RERUN_STARTERS[job_type] = starter


def get_starter(job_type: str | None) -> RerunStarter | None:
    return _RERUN_STARTERS.get(job_type or "")
