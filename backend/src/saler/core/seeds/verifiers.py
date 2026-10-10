"""外部公开来源校验（FR-014）：默认 Wikipedia 佐证，追加式写 validation_record。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session, sessionmaker

from saler.db.models import GraphNode, Seed, ValidationRecord
from saler.jobs.engine import JobContext

USER_AGENT = "SalerTool/0.1 (business contact validation; local desktop app)"


@dataclass
class ValidationCheck:
    status: str  # found / not_found / ambiguous / error
    confidence: float
    evidence_url: str | None = None
    detail: str = ""


def _norm(text: str) -> str:
    return (
        (text or "")
        .lower()
        .replace("co., ltd", "")
        .replace("co.,ltd", "")
        .replace("inc.", "")
        .replace("ltd.", "")
        .replace("ltd", "")
        .replace("co.", "")
        .replace("company", "")
        .strip(" .,-")
    )


class WikipediaVerifier:
    provider = "wikipedia"

    def __init__(self, getter: Callable[[str, dict], Awaitable[dict]] | None = None) -> None:
        self._getter = getter or self._default_getter

    @staticmethod
    async def _default_getter(url: str, params: dict) -> dict:
        async with httpx.AsyncClient(trust_env=True, timeout=15) as client:
            resp = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            return resp.json()

    async def check(self, name: str) -> ValidationCheck:
        last_error: str | None = None
        for host in ("en.wikipedia.org", "zh.wikipedia.org"):
            try:
                data = await self._getter(
                    f"https://{host}/w/api.php",
                    {
                        "action": "query",
                        "list": "search",
                        "srsearch": name,
                        "format": "json",
                        "srlimit": 3,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - 校验失败记为 error
                last_error = f"{type(exc).__name__}: {exc}"
                continue
            hits = (((data or {}).get("query") or {}).get("search")) or []
            if not hits:
                continue
            top = (hits[0].get("title") or "").strip()
            url = f"https://{host}/wiki/{top.replace(' ', '_')}"
            if _norm(name) == _norm(top):
                return ValidationCheck("found", 0.8, url, top)
            tokens = set(_norm(name).split())
            overlap = len(tokens & set(_norm(top).split())) / max(1, len(tokens))
            if overlap >= 0.5:
                return ValidationCheck("ambiguous", 0.45, url, top)
        if last_error:
            return ValidationCheck("error", 0.0, None, last_error)
        return ValidationCheck("not_found", 0.1)


async def run_validation(
    ctx: JobContext,
    session_factory: sessionmaker[Session],
    *,
    payload: dict,
    verifier: WikipediaVerifier | None = None,
    delay_s: float = 1.0,
) -> dict:
    verifier = verifier or WikipediaVerifier()
    node_ids = payload.get("node_ids") or []
    seed_ids = payload.get("seed_ids") or []
    targets = [("graph_node", node_id) for node_id in node_ids] + [
        ("seed", seed_id) for seed_id in seed_ids
    ]
    if not targets:
        return {"checked": 0, "found": 0, "ambiguous": 0, "not_found": 0, "errors": 0}

    results = {"checked": 0, "found": 0, "ambiguous": 0, "not_found": 0, "errors": 0}
    for target_type, target_id in targets:
        await ctx.checkpoint()
        with session_factory() as db:
            obj = db.get(GraphNode if target_type == "graph_node" else Seed, target_id)
            if obj is None:
                continue
            name = obj.name if target_type == "graph_node" else obj.query.strip().strip('"')
        try:
            check = await verifier.check(name)
        except Exception as exc:  # noqa: BLE001
            check = ValidationCheck("error", 0.0, None, str(exc))
        with session_factory() as db:
            obj = db.get(GraphNode if target_type == "graph_node" else Seed, target_id)
            if obj is not None:
                db.add(
                    ValidationRecord(
                        target_type=target_type,
                        target_id=target_id,
                        provider=verifier.provider,
                        status=check.status,
                        confidence=check.confidence,
                        evidence_url=check.evidence_url,
                    )
                )
                if check.status in ("found", "ambiguous") and obj.confidence is None:
                    obj.confidence = check.confidence
                db.commit()
        results["checked"] += 1
        bucket = check.status if check.status in results else "errors"
        results[bucket] += 1
        ctx.progress(checked=results["checked"], total=len(targets))
        if delay_s:
            await asyncio.sleep(delay_s)  # 礼貌限速
    return results
