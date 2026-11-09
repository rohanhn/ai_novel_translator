"""Bộ quản lý job dịch trong process (design D4).

- Mỗi chương tối đa một job (registry theo (novel_id, index)).
- Hai làn chạy, mỗi làn một thread và chạy tối đa một job một lúc:
  FOREGROUND (chương chủ sở hữu mở) và BACKGROUND (prefetch). Chương vừa mở không phải chờ
  prefetch đang chạy; tối đa hai request song song.
- Job giữ toàn bộ sự kiện đã phát; subscriber đăng ký muộn được phát lại từ đầu rồi nhận tiếp.
- Foreground mở đúng chương đang có job: gắn vào job đó. Job còn chờ trong làn background thì
  được nâng sang làn foreground (dùng policy FOREGROUND); job đã chạy thì giữ nguyên.
- Chỉ hủy được job còn chờ; job đã gửi request chạy đến hết.
"""

from __future__ import annotations

import queue
import threading
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..domain.models import ChainEvent, ChainPolicy
from ..domain.ports import DailyQuotaError, RateQuotaError, TranslationError
from ..pipeline.sections import Paragraph, Title
from .services import NotFoundError, TranslationService

TERMINAL = frozenset({"completed", "failed", "quota_exhausted", "cancelled"})


class Lane(str, Enum):
    FOREGROUND = "foreground"
    BACKGROUND = "background"


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"


@dataclass(frozen=True)
class JobEvent:
    """Sự kiện gửi cho subscriber. type: title | paragraph | waiting_for_quota | fallback_step
    | completed | failed | quota_exhausted | cancelled (4 loại cuối là sự kiện kết thúc)."""

    type: str
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return self.type in TERMINAL


class Job:
    def __init__(self, novel_id: int, index: int, lane: Lane, force: bool = False):
        self.novel_id = novel_id
        self.index = index
        self.lane = lane
        self.force = force
        self.state = JobState.QUEUED
        self._events: list[JobEvent] = []
        self._subscribers: list[queue.Queue[JobEvent]] = []
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._paragraphs = 0

    @property
    def key(self) -> tuple[int, int]:
        return (self.novel_id, self.index)

    @property
    def policy(self) -> ChainPolicy:
        return ChainPolicy.FOREGROUND if self.lane == Lane.FOREGROUND else ChainPolicy.BACKGROUND

    @property
    def events(self) -> list[JobEvent]:
        with self._lock:
            return list(self._events)

    def publish(self, event: JobEvent) -> None:
        with self._lock:
            if self._done.is_set():
                return
            self._events.append(event)
            subscribers = list(self._subscribers)
            if event.terminal:
                self._done.set()
        for q in subscribers:
            q.put(event)

    def subscribe(self) -> Iterator[JobEvent]:
        """Phát lại mọi sự kiện đã có rồi các sự kiện mới, dừng sau sự kiện kết thúc."""
        q: queue.Queue[JobEvent] = queue.Queue()
        with self._lock:
            backlog = list(self._events)
            if not self._done.is_set():
                self._subscribers.append(q)
        return self._iterate(backlog, q)

    def _iterate(self, backlog: list[JobEvent], q: queue.Queue[JobEvent]) -> Iterator[JobEvent]:
        try:
            for ev in backlog:
                yield ev
                if ev.terminal:
                    return
            while True:
                ev = q.get()
                yield ev
                if ev.terminal:
                    return
        finally:
            with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)

    def wait(self, timeout: float | None = None) -> bool:
        return self._done.wait(timeout)

    @property
    def terminal_event(self) -> JobEvent | None:
        with self._lock:
            return self._events[-1] if self._events and self._events[-1].terminal else None

    # chuyển sự kiện của pipeline → JobEvent
    def on_pipeline_event(self, ev: Any) -> None:
        if isinstance(ev, Paragraph):
            self._paragraphs += 1
            self.publish(JobEvent("paragraph", {"index": self._paragraphs, "text": ev.text}))
        elif isinstance(ev, Title):
            self.publish(JobEvent("title", {"text": ev.text}))
        elif isinstance(ev, ChainEvent):
            self.publish(JobEvent(ev.kind, {"step": ev.step, "provider": ev.provider,
                                            "model": ev.model, "delay": ev.delay}))


class _LaneWorker:
    def __init__(self, manager: TranslationJobManager, lane: Lane):
        self.manager = manager
        self.lane = lane
        self.pending: deque[Job] = deque()
        self.running: Job | None = None
        self.thread = threading.Thread(target=self._loop, name=f"jobs-{lane.value}", daemon=True)

    def _loop(self) -> None:
        m = self.manager
        while True:
            with m._cond:
                while not self.pending and not m._stopping:
                    m._cond.wait()
                if m._stopping:
                    return
                job = self.pending.popleft()
                job.state = JobState.RUNNING
                self.running = job
            try:
                m._run(job)
            finally:
                with m._cond:
                    self.running = None
                    job.state = JobState.DONE
                    if m._jobs.get(job.key) is job:
                        del m._jobs[job.key]
                    m._cond.notify_all()


class TranslationJobManager:
    def __init__(self, translation: TranslationService, autostart: bool = True):
        self.translation = translation
        self._jobs: dict[tuple[int, int], Job] = {}
        self._cond = threading.Condition()
        self._stopping = False
        self._lanes = {lane: _LaneWorker(self, lane) for lane in Lane}
        if autostart:
            self.start()

    def start(self) -> None:
        for w in self._lanes.values():
            if not w.thread.is_alive():
                w.thread.start()

    def shutdown(self) -> None:
        with self._cond:
            self._stopping = True
            self._cond.notify_all()

    # --- API ---
    def submit(self, novel_id: int, index: int, lane: Lane = Lane.FOREGROUND,
               force: bool = False) -> Job:
        """Tạo job hoặc trả về job đang có của chương (nâng làn nếu cần)."""
        with self._cond:
            job = self._jobs.get((novel_id, index))
            if job is not None:
                if (lane == Lane.FOREGROUND and job.lane == Lane.BACKGROUND
                        and job.state == JobState.QUEUED):
                    self._lanes[Lane.BACKGROUND].pending.remove(job)
                    job.lane = Lane.FOREGROUND
                    self._lanes[Lane.FOREGROUND].pending.append(job)
                    self._cond.notify_all()
                return job
            job = Job(novel_id, index, lane, force)
            self._jobs[job.key] = job
            self._lanes[lane].pending.append(job)
            self._cond.notify_all()
            return job

    def get(self, novel_id: int, index: int) -> Job | None:
        with self._cond:
            return self._jobs.get((novel_id, index))

    def cancel(self, novel_id: int, index: int) -> bool:
        """Hủy job còn chờ; job đang chạy (đã gửi request) thì không hủy."""
        with self._cond:
            job = self._jobs.get((novel_id, index))
            if job is None or job.state != JobState.QUEUED:
                return False
            self._lanes[job.lane].pending.remove(job)
            del self._jobs[job.key]
            job.state = JobState.DONE
        job.publish(JobEvent("cancelled"))
        return True

    def cancel_queued_for_novel(self, novel_id: int, lane: Lane | None = None) -> int:
        with self._cond:
            keys = [k for k, j in self._jobs.items()
                    if k[0] == novel_id and j.state == JobState.QUEUED
                    and (lane is None or j.lane == lane)]
        return sum(self.cancel(*k) for k in keys)

    def is_busy(self, lane: Lane) -> bool:
        with self._cond:
            w = self._lanes[lane]
            return w.running is not None or bool(w.pending)

    # --- chạy job ---
    def _run(self, job: Job) -> None:
        try:
            ch = self.translation.translate_chapter(
                job.novel_id, job.index, force=job.force, policy=job.policy,
                on_event=job.on_pipeline_event,
            )
        except DailyQuotaError as e:
            job.publish(JobEvent("quota_exhausted", {
                "reset_at": e.reset_at.isoformat() if e.reset_at else None, "message": str(e)}))
        except RateQuotaError as e:
            job.publish(JobEvent("failed", {"category": e.category, "message": str(e)}))
        except TranslationError as e:
            job.publish(JobEvent("failed", {"category": e.category, "message": str(e)}))
        except NotFoundError as e:
            job.publish(JobEvent("failed", {"category": "not_found", "message": str(e)}))
        except Exception as e:  # lỗi không lường trước: vẫn phải kết thúc job cho subscriber
            job.publish(JobEvent("failed", {"category": "internal", "message": str(e)}))
            raise
        else:
            job.publish(JobEvent("completed", {
                "status": ch.status.value, "title": ch.translated_title,
                "provider": ch.provider, "model": ch.model, "chain_step": ch.chain_step,
                "possible_omission": ch.possible_omission,
            }))
