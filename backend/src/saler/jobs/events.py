"""任务进度事件总线（SSE 订阅源）。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

MAX_QUEUE = 500


@dataclass
class JobEvent:
    type: str  # progress / log / done / error
    data: dict = field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._queues: dict[int, asyncio.Queue[JobEvent]] = {}

    def subscribe(self, job_id: int) -> asyncio.Queue[JobEvent]:
        q = self._queues.get(job_id)
        if q is None:
            q = asyncio.Queue(maxsize=MAX_QUEUE)
            self._queues[job_id] = q
        return q

    def publish(self, job_id: int, event: JobEvent) -> None:
        q = self._queues.get(job_id)
        if q is None:
            return
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            # 丢最旧，保最新（进度类事件允许降级）
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def discard(self, job_id: int, queue: asyncio.Queue[JobEvent]) -> None:
        if self._queues.get(job_id) is queue:
            self._queues.pop(job_id, None)

    def close(self, job_id: int) -> None:
        self._queues.pop(job_id, None)
