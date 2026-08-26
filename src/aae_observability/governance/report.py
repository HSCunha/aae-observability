"""Operational governance reporting with bounded dimensions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from threading import RLock
from types import MappingProxyType

from aae_observability.governance.audit import GovernanceAuditRecord, GovernanceAuditSink


@dataclass(frozen=True, slots=True)
class GovernanceReportSnapshot:
    total: int
    verdicts: Mapping[str, int]
    outcomes: Mapping[str, int]
    operations: Mapping[str, int]
    frameworks: Mapping[str, int]
    policies: Mapping[str, int]
    rules: Mapping[str, int]
    average_duration_ms: float
    maximum_duration_ms: float
    dropped_dimensions: int


class GovernanceReport(GovernanceAuditSink):
    def __init__(
        self,
        *,
        aggregate_by_policy: bool = True,
        aggregate_by_rule: bool = False,
        max_distinct_policies: int = 100,
        max_distinct_rules: int = 500,
    ) -> None:
        if max_distinct_policies < 1 or max_distinct_rules < 1:
            raise ValueError("dimension limits must be positive")
        self.aggregate_by_policy = aggregate_by_policy
        self.aggregate_by_rule = aggregate_by_rule
        self.max_distinct_policies = max_distinct_policies
        self.max_distinct_rules = max_distinct_rules
        self._lock = RLock()
        self._total = 0
        self._duration = 0.0
        self._max_duration = 0.0
        self._dropped = 0
        self._verdicts = Counter()
        self._outcomes = Counter()
        self._operations = Counter()
        self._frameworks = Counter()
        self._policies = Counter()
        self._rules = Counter()

    def _bounded_add(self, counter: Counter[str], key: str | None, limit: int) -> None:
        if not key:
            return
        if key in counter or len(counter) < limit:
            counter[key] += 1
        else:
            self._dropped += 1

    def emit(self, record: GovernanceAuditRecord) -> None:
        with self._lock:
            self._total += 1
            self._duration += record.duration_ms
            self._max_duration = max(self._max_duration, record.duration_ms)
            self._verdicts[record.verdict] += 1
            self._outcomes[record.outcome] += 1
            self._operations[record.operation] += 1
            self._frameworks[record.framework] += 1
            if self.aggregate_by_policy:
                self._bounded_add(self._policies, record.policy_name, self.max_distinct_policies)
            if self.aggregate_by_rule:
                self._bounded_add(self._rules, record.rule_id, self.max_distinct_rules)

    def snapshot(self) -> GovernanceReportSnapshot:
        with self._lock:

            def freeze(c):
                return MappingProxyType(dict(c))

            return GovernanceReportSnapshot(
                self._total,
                freeze(self._verdicts),
                freeze(self._outcomes),
                freeze(self._operations),
                freeze(self._frameworks),
                freeze(self._policies),
                freeze(self._rules),
                self._duration / self._total if self._total else 0.0,
                self._max_duration,
                self._dropped,
            )


class CompositeGovernanceAuditSink:
    """Fan out records while isolating failures from every destination."""

    def __init__(self, *sinks: GovernanceAuditSink) -> None:
        self.sinks = tuple(sinks)
        self.failures = 0

    def emit(self, record: GovernanceAuditRecord) -> None:
        for sink in self.sinks:
            try:
                sink.emit(record)
            except Exception:
                self.failures += 1

    def flush(self, timeout_ms: int = 30_000) -> bool:
        result = True
        for sink in self.sinks:
            method = getattr(sink, "flush", None)
            if callable(method):
                try:
                    result = bool(method(timeout_ms)) and result
                except Exception:
                    self.failures += 1
                    result = False
        return result

    def close(self, timeout_ms: int = 30_000) -> None:
        for sink in self.sinks:
            method = getattr(sink, "close", None)
            if callable(method):
                try:
                    method(timeout_ms)
                except Exception:
                    self.failures += 1
