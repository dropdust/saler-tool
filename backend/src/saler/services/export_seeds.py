"""种子清单导出（contracts/data-exchange.md §1；FR-016）。"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from saler.core.errors import ValidationFailed
from saler.core.seeds import service as seed_service
from saler.db.models import GraphNode, Seed

CSV_COLUMNS = [
    "query",
    "lang",
    "priority",
    "batch",
    "product_line",
    "persona",
    "market",
    "status",
    "source",
    "source_entity",
]


def export_seeds(
    db: Session,
    *,
    fmt: str,
    out_dir: Path,
    batch: str | None = None,
    status: str | None = None,
    review_status: str | None = "approved",
    market_id: int | None = None,
    lang: str | None = None,
    source: str | None = None,
    max_priority: int | None = None,
    limit: int | None = None,
) -> dict:
    if fmt not in ("txt", "csv"):
        raise ValidationFailed("format 必须为 txt 或 csv")
    query = seed_service.list_seeds(
        db,
        batch=batch,
        status=status,
        review_status=review_status,
        market_id=market_id,
        lang=lang,
        source=source,
        sort="priority",
    )
    if max_priority:
        query = query.filter(Seed.priority <= max_priority)
    if limit:
        query = query.limit(limit)
    seeds = query.all()

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    node_names = {node.id: node.name for node in db.query(GraphNode).all()}

    if fmt == "csv":
        path = out_dir / f"seeds-{stamp}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for seed in seeds:
                writer.writerow(
                    {
                        "query": seed.query,
                        "lang": seed.lang,
                        "priority": seed.priority,
                        "batch": seed.batch or "",
                        "product_line": node_names.get(seed.product_line_id, ""),
                        "persona": node_names.get(seed.persona_id, ""),
                        "market": node_names.get(seed.market_id, ""),
                        "status": seed.status,
                        "source": seed.source,
                        "source_entity": node_names.get(seed.source_node_id, ""),
                    }
                )
    else:
        path = out_dir / f"seeds-{stamp}.txt"
        header = f"# exported={datetime.now(UTC).isoformat()} count={len(seeds)}"
        path.write_text("\n".join([header, *(seed.query for seed in seeds)]) + "\n", encoding="utf-8")
    return {"path": str(path), "count": len(seeds)}
