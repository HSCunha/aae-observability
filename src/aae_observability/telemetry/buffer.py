"""Bounded, thread-safe, non-blocking telemetry buffer."""

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from threading import Lock

from aae_observability.config import DropPolicy
from aae_observability.telemetry.envelope import TelemetryEnvelope


@dataclass(frozen=True, slots=True)
class BufferStats:
    capacity: int
    current_size: int
    total_accepted: int
    total_dropped: int
    dropped_oldest: int
    dropped_new: int
    lock_contention_drops: int
    high_water_mark: int
    closed: bool


class TelemetryBuffer:
    def __init__(self, capacity: int, drop_policy: DropPolicy = DropPolicy.DROP_OLDEST) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self._capacity = capacity
        self._drop_policy = drop_policy
        self._items: deque[TelemetryEnvelope] = deque()
        self._lock = Lock()
        self._accepted = 0
        self._dropped_oldest = 0
        self._dropped_new = 0
        self._contention_drops = 0
        self._high_water_mark = 0
        self._closed = False

    @property
    def capacity(self) -> int:
        return self._capacity

    def offer(self, envelope: TelemetryEnvelope) -> bool:
        if not self._lock.acquire(blocking=False):
            self._contention_drops += 1
            return False
        try:
            if self._closed:
                self._dropped_new += 1
                return False
            if len(self._items) >= self._capacity:
                if self._drop_policy is DropPolicy.DROP_NEW:
                    self._dropped_new += 1
                    return False
                self._items.popleft()
                self._dropped_oldest += 1
            self._items.append(envelope)
            self._accepted += 1
            self._high_water_mark = max(self._high_water_mark, len(self._items))
            return True
        finally:
            self._lock.release()

    def offer_many(self, envelopes: Iterable[TelemetryEnvelope]) -> int:
        return sum(1 for e in envelopes if self.offer(e))

    def drain(self, max_items: int | None = None) -> tuple[TelemetryEnvelope, ...]:
        if max_items is not None and max_items < 1:
            raise ValueError("max_items must be at least 1 when supplied")
        with self._lock:
            count = len(self._items) if max_items is None else min(max_items, len(self._items))
            return tuple(self._items.popleft() for _ in range(count))

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def stats(self) -> BufferStats:
        with self._lock:
            dropped = self._dropped_oldest + self._dropped_new + self._contention_drops
            return BufferStats(
                self._capacity,
                len(self._items),
                self._accepted,
                dropped,
                self._dropped_oldest,
                self._dropped_new,
                self._contention_drops,
                self._high_water_mark,
                self._closed,
            )
