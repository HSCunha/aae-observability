"""Swappable telemetry sink contract."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TelemetrySink(Protocol):
    """Destination contract for spans, metrics, and logs."""

    def emit(
        self,
        spans: Sequence[Any] = (),
        metrics: Sequence[Any] = (),
        logs: Sequence[Any] = (),
    ) -> None:
        """Accept telemetry without blocking the instrumented call path."""
        ...

    def force_flush(self, timeout_ms: int = 30_000) -> bool:
        """Flush buffered telemetry within the supplied timeout."""
        ...

    def shutdown(self, timeout_ms: int = 30_000) -> None:
        """Release telemetry resources within the supplied timeout."""
        ...


class BaseTelemetrySink(ABC):
    """Inheritance-based convenience contract for telemetry sinks."""

    @abstractmethod
    def emit(
        self,
        spans: Sequence[Any] = (),
        metrics: Sequence[Any] = (),
        logs: Sequence[Any] = (),
    ) -> None:
        """Accept a telemetry batch."""
        raise NotImplementedError

    def force_flush(self, timeout_ms: int = 30_000) -> bool:
        del timeout_ms
        return True

    def shutdown(self, timeout_ms: int = 30_000) -> None:
        del timeout_ms


class NullTelemetrySink(BaseTelemetrySink):
    """Bootstrap sink that counts and discards telemetry."""

    def __init__(self) -> None:
        self.emitted_spans = 0
        self.emitted_metrics = 0
        self.emitted_logs = 0
        self.flush_count = 0
        self.shutdown_called = False

    def emit(
        self,
        spans: Sequence[Any] = (),
        metrics: Sequence[Any] = (),
        logs: Sequence[Any] = (),
    ) -> None:
        self.emitted_spans += len(spans)
        self.emitted_metrics += len(metrics)
        self.emitted_logs += len(logs)

    def force_flush(self, timeout_ms: int = 30_000) -> bool:
        del timeout_ms
        self.flush_count += 1
        return True

    def shutdown(self, timeout_ms: int = 30_000) -> None:
        del timeout_ms
        self.shutdown_called = True
