from dataclasses import dataclass

from opentelemetry.metrics import Counter, Histogram, Meter

from aae_observability.telemetry.buffer import BufferStats


@dataclass(slots=True)
class BufferMetrics:
    dropped: Counter
    utilization: Histogram
    _last_dropped: int = 0

    @classmethod
    def create(cls, meter: Meter) -> "BufferMetrics":
        return cls(
            meter.create_counter("aae.observability.telemetry.buffer.dropped", unit="{record}"),
            meter.create_histogram("aae.observability.telemetry.buffer.utilization", unit="1"),
        )

    def observe(self, stats: BufferStats) -> None:
        delta = max(0, stats.total_dropped - self._last_dropped)
        if delta:
            self.dropped.add(delta, {"aae.observability.buffer.closed": str(stats.closed).lower()})
        self._last_dropped = stats.total_dropped
        self.utilization.record(stats.current_size / stats.capacity)
