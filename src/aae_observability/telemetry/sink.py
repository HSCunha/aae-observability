from collections.abc import Callable, Sequence
from typing import Any

from aae_observability.contracts.telemetry import BaseTelemetrySink
from aae_observability.telemetry.buffer import BufferStats, TelemetryBuffer
from aae_observability.telemetry.buffer_metrics import BufferMetrics
from aae_observability.telemetry.envelope import SignalType, TelemetryEnvelope

DrainHandler = Callable[[tuple[TelemetryEnvelope, ...]], bool]


class BufferedTelemetrySink(BaseTelemetrySink):
    def __init__(
        self,
        buffer: TelemetryBuffer,
        drain_handler: DrainHandler | None = None,
        buffer_metrics: BufferMetrics | None = None,
    ) -> None:
        self.buffer = buffer
        self._drain_handler = drain_handler
        self._buffer_metrics = buffer_metrics
        self.shutdown_called = False

    def _observe(self) -> None:
        if self._buffer_metrics:
            self._buffer_metrics.observe(self.buffer.stats())

    def emit(
        self, spans: Sequence[Any] = (), metrics: Sequence[Any] = (), logs: Sequence[Any] = ()
    ) -> None:
        self.buffer.offer_many(TelemetryEnvelope(SignalType.SPAN, x) for x in spans)
        self.buffer.offer_many(TelemetryEnvelope(SignalType.METRIC, x) for x in metrics)
        self.buffer.offer_many(TelemetryEnvelope(SignalType.LOG, x) for x in logs)
        self._observe()

    def force_flush(self, timeout_ms: int = 30000) -> bool:
        del timeout_ms
        if self._drain_handler is None:
            return self.buffer.stats().current_size == 0
        batch = self.buffer.drain()
        if not batch:
            self._observe()
            return True
        if self._drain_handler(batch):
            self._observe()
            return True
        self.buffer.offer_many(batch)
        self._observe()
        return False

    def shutdown(self, timeout_ms: int = 30000) -> None:
        self.buffer.close()
        self.force_flush(timeout_ms)
        self.shutdown_called = True

    def stats(self) -> BufferStats:
        return self.buffer.stats()
