"""Privacy-safe governance audit records and durable exporters."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import RLock
from time import time_ns
from typing import Protocol, runtime_checkable

from aae_observability.contracts import AgentCall
from aae_observability.types import PolicyResult

SCHEMA_VERSION = "aae-observability.audit/v1"


@dataclass(frozen=True, slots=True)
class GovernanceAuditRecord:
    verdict: str
    outcome: str
    operation: str
    framework: str
    rule_id: str | None = None
    policy_name: str | None = None
    duration_ms: float = 0.0
    timestamp_ns: int = field(default_factory=time_ns)

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": SCHEMA_VERSION, **asdict(self)}


@runtime_checkable
class GovernanceAuditSink(Protocol):
    def emit(self, record: GovernanceAuditRecord) -> None: ...


class InMemoryGovernanceAuditSink:
    def __init__(self) -> None:
        self.records: list[GovernanceAuditRecord] = []

    def emit(self, record: GovernanceAuditRecord) -> None:
        self.records.append(record)


@dataclass(frozen=True, slots=True)
class AuditExporterStats:
    written: int
    failed: int
    rotations: int
    closed: bool


class JsonLinesGovernanceAuditSink:
    """Thread-safe JSONL exporter with bounded rotation and failure isolation."""

    def __init__(
        self,
        path: str | Path,
        *,
        max_bytes: int = 10_000_000,
        rotation_count: int = 3,
        flush_every: int = 1,
    ) -> None:
        if max_bytes < 256:
            raise ValueError("max_bytes must be at least 256")
        if rotation_count < 0:
            raise ValueError("rotation_count must be non-negative")
        if flush_every < 1:
            raise ValueError("flush_every must be at least 1")
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.rotation_count = rotation_count
        self.flush_every = flush_every
        self._lock = RLock()
        self._file = None
        self._written = 0
        self._failed = 0
        self._rotations = 0
        self._pending = 0
        self._closed = False
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _open(self):
        if self._file is None:
            self._file = self.path.open("a", encoding="utf-8")

    def _rotate(self, incoming: int) -> None:
        size = self.path.stat().st_size if self.path.exists() else 0
        if size + incoming <= self.max_bytes:
            return
        if self._file:
            self._file.flush()
            self._file.close()
            self._file = None
        if self.rotation_count == 0:
            self.path.write_text("", encoding="utf-8")
            self._rotations += 1
            return
        oldest = self.path.with_name(f"{self.path.name}.{self.rotation_count}")
        if oldest.exists():
            oldest.unlink()
        for index in range(self.rotation_count - 1, 0, -1):
            source = self.path.with_name(f"{self.path.name}.{index}")
            if source.exists():
                os.replace(source, self.path.with_name(f"{self.path.name}.{index + 1}"))
        if self.path.exists():
            os.replace(self.path, self.path.with_name(f"{self.path.name}.1"))
        self._rotations += 1

    def emit(self, record: GovernanceAuditRecord) -> None:
        with self._lock:
            if self._closed:
                self._failed += 1
                return
            try:
                line = (
                    json.dumps(
                        record.to_dict(), separators=(",", ":"), sort_keys=True, ensure_ascii=False
                    )
                    + "\n"
                )
                encoded = len(line.encode("utf-8"))
                if encoded > self.max_bytes:
                    self._failed += 1
                    return
                self._rotate(encoded)
                self._open()
                self._file.write(line)
                self._pending += 1
                self._written += 1
                if self._pending >= self.flush_every:
                    self._file.flush()
                    self._pending = 0
            except (OSError, TypeError, ValueError):
                self._failed += 1

    def flush(self, timeout_ms: int = 30_000) -> bool:
        del timeout_ms
        with self._lock:
            try:
                if self._file:
                    self._file.flush()
                self._pending = 0
                return True
            except OSError:
                self._failed += 1
                return False

    def close(self, timeout_ms: int = 30_000) -> None:
        del timeout_ms
        with self._lock:
            if self._closed:
                return
            self.flush()
            if self._file:
                self._file.close()
                self._file = None
            self._closed = True

    def stats(self) -> AuditExporterStats:
        with self._lock:
            return AuditExporterStats(self._written, self._failed, self._rotations, self._closed)


def build_audit_record(
    call: AgentCall, result: PolicyResult, outcome: str, duration_ms: float
) -> GovernanceAuditRecord:
    op = getattr(call.operation, "value", call.operation) or (
        "tool.call" if call.tool_name else "agent.run"
    )
    policy = result.metadata.get("policy") if isinstance(result.metadata, dict) else None
    return GovernanceAuditRecord(
        result.verdict.value,
        outcome,
        str(op),
        call.framework.value,
        result.rule_id,
        str(policy) if policy else None,
        duration_ms,
    )
