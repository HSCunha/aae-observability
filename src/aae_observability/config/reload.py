"""Thread-safe polling and atomic runtime configuration reload."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from aae_observability.config.layered import load_layered_config
from aae_observability.config.models import (
    AaeObservabilityConfig,
    GovernanceConfig,
    TelemetryConfig,
)

_LOGGER = logging.getLogger("aae.observability.config.reload")


@dataclass(frozen=True, slots=True)
class ReloadEvent:
    """Privacy-safe outcome of one reload attempt."""

    outcome: str
    generation: int
    changed_sources: tuple[str, ...]
    timestamp_ns: int
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class ReloadSnapshot:
    """Immutable operational snapshot for reload monitoring."""

    generation: int
    successful_reloads: int
    failed_reloads: int
    last_event: ReloadEvent | None
    watched_sources: tuple[str, ...]


ReloadCallback = Callable[[AaeObservabilityConfig], None]
ReloadEventSink = Callable[[ReloadEvent], None]
ConfigLoader = Callable[[], AaeObservabilityConfig]


class RuntimeConfigReloader:
    """Poll files and atomically publish fully validated configuration generations.

    A failed load or callback leaves the previous generation active. File contents,
    configuration values, policy values, and exception text are never emitted.
    """

    def __init__(
        self,
        loader: ConfigLoader,
        callback: ReloadCallback,
        sources: Sequence[str | Path],
        *,
        interval_ms: int = 1_000,
        event_sink: ReloadEventSink | None = None,
        clock_ns: Callable[[], int] = time.time_ns,
    ) -> None:
        if interval_ms < 100:
            raise ValueError("interval_ms must be at least 100")
        normalized = tuple(Path(source).resolve() for source in sources)
        if not normalized:
            raise ValueError("at least one reload source is required")
        self._loader = loader
        self._callback = callback
        self._sources = normalized
        self._interval = interval_ms / 1_000
        self._event_sink = event_sink
        self._clock_ns = clock_ns
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._generation = 0
        self._successful = 0
        self._failed = 0
        self._last_event: ReloadEvent | None = None
        self._signatures = self._read_signatures()

    @staticmethod
    def _signature(path: Path) -> tuple[int, int] | None:
        try:
            stat = path.stat()
            return stat.st_mtime_ns, stat.st_size
        except OSError:
            return None

    def _read_signatures(self) -> Mapping[Path, tuple[int, int] | None]:
        return MappingProxyType({path: self._signature(path) for path in self._sources})

    def _emit(self, event: ReloadEvent) -> None:
        with self._lock:
            self._last_event = event
        if self._event_sink is not None:
            try:
                self._event_sink(event)
            except Exception:
                _LOGGER.warning("reload event sink failed", exc_info=False)

    def check_now(self, *, force: bool = False) -> bool:
        """Check sources once and apply one atomic generation when changed."""
        signatures = self._read_signatures()
        changed = tuple(
            path.name for path in self._sources if signatures[path] != self._signatures[path]
        )
        if not force and not changed:
            return False
        try:
            candidate = self._loader()
            self._callback(candidate)
        except Exception as exc:
            with self._lock:
                self._failed += 1
                generation = self._generation
            self._emit(
                ReloadEvent("failure", generation, changed, self._clock_ns(), type(exc).__name__)
            )
            return False
        with self._lock:
            self._signatures = signatures
            self._generation += 1
            self._successful += 1
            generation = self._generation
        self._emit(ReloadEvent("success", generation, changed, self._clock_ns()))
        return True

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self.check_now()

    def start(self) -> None:
        """Start the idempotent daemon watcher."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, name="aae-observability-config-reloader", daemon=True
            )
            self._thread.start()

    def stop(self, timeout_ms: int = 30_000) -> None:
        """Stop the watcher within the supplied timeout."""
        self._stop.set()
        with self._lock:
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0, timeout_ms) / 1_000)

    def snapshot(self) -> ReloadSnapshot:
        with self._lock:
            return ReloadSnapshot(
                self._generation,
                self._successful,
                self._failed,
                self._last_event,
                tuple(str(path) for path in self._sources),
            )


def build_layered_reloader(
    config_file: str | Path,
    callback: ReloadCallback,
    *,
    telemetry: TelemetryConfig | None = None,
    governance: GovernanceConfig | None = None,
    environ: Mapping[str, str] | None = None,
    policy_source: str | Path | None = None,
    interval_ms: int = 1_000,
    event_sink: ReloadEventSink | None = None,
) -> RuntimeConfigReloader:
    """Build a reloader using the Release 0.5.0 layered configuration semantics."""
    sources: list[str | Path] = [config_file]
    if policy_source is not None:
        sources.append(policy_source)
    return RuntimeConfigReloader(
        lambda: load_layered_config(
            config_file, telemetry=telemetry, governance=governance, environ=environ
        ),
        callback,
        sources,
        interval_ms=interval_ms,
        event_sink=event_sink,
    )
