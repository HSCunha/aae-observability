"""Network-free and opt-in-live round-trip integration helpers."""

from __future__ import annotations

import itertools
import json
import threading
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CapturedEvent:
    body: bytes
    partition_key: str | None = None


@dataclass(frozen=True, slots=True)
class IntegrationReport:
    expected: int
    received: int
    duplicates: int
    missing_ids: tuple[str, ...]
    unexpected_ids: tuple[str, ...]
    ordered: bool
    valid: bool


@dataclass(slots=True)
class MockAgent:
    name: str = "integration-agent"
    calls: int = 0

    def invoke(self, value: str, *, correlation_id: str) -> dict[str, str]:
        self.calls += 1
        return {"value": value, "correlation_id": correlation_id, "agent": self.name}


class MockMicrosoftAgent(MockAgent):
    __aae_observability_framework__ = "microsoft_agent_framework"

    def run(self, value: str, *, correlation_id: str = "maf-1") -> dict[str, str]:
        return self.invoke(value, correlation_id=correlation_id)


class MockLangChainAgent(MockAgent):
    __aae_observability_framework__ = "langchain"


class MockMultiAgentWorkflow:
    __aae_observability_framework__ = "multi_agent"

    def __init__(self) -> None:
        self.handoffs: list[tuple[str, str, str]] = []

    def handoff(self, source: str, target: str, *, correlation_id: str) -> dict[str, str]:
        self.handoffs.append((source, target, correlation_id))
        return {"source": source, "target": target, "correlation_id": correlation_id}


class FakeEventHubProducer:
    """Thread-safe byte-preserving Event Hub producer double."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[CapturedEvent] = []
        self.closed = False

    def send(self, body: bytes, *, partition_key: str | None = None) -> None:
        if self.closed:
            raise RuntimeError("producer is closed")
        with self._lock:
            self._events.append(CapturedEvent(bytes(body), partition_key))

    def snapshot(self) -> tuple[CapturedEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def close(self) -> None:
        self.closed = True


class ChaosEventHubProducer:
    """Inject deterministic transient failures and retry with bounded backoff."""

    def __init__(
        self,
        producer: FakeEventHubProducer,
        *,
        failures_before_success: int = 0,
        max_retries: int = 3,
        base_delay_ms: int = 1,
        sleeper=time.sleep,
    ) -> None:
        if failures_before_success < 0 or max_retries < 0:
            raise ValueError("retry values must be non-negative")
        self.producer = producer
        self.remaining_failures = failures_before_success
        self.max_retries = max_retries
        self.base_delay_ms = base_delay_ms
        self.sleeper = sleeper
        self.attempts = 0
        self.retries = 0
        self.failures = 0

    def send(self, body: bytes, *, partition_key: str | None = None) -> None:
        for attempt in range(self.max_retries + 1):
            self.attempts += 1
            try:
                if self.remaining_failures:
                    self.remaining_failures -= 1
                    raise TimeoutError("transient Event Hub failure")
                self.producer.send(body, partition_key=partition_key)
                return
            except TimeoutError:
                self.failures += 1
                if attempt >= self.max_retries:
                    raise
                self.retries += 1
                self.sleeper((self.base_delay_ms * (2**attempt)) / 1000)


class RoundTripVerifier:
    """Reconcile emitted and consumed record IDs and per-partition order."""

    @staticmethod
    def decode(events: Iterable[CapturedEvent]) -> tuple[Mapping[str, Any], ...]:
        return tuple(json.loads(event.body.decode("utf-8")) for event in events)

    def verify(
        self, expected_ids: Iterable[str], events: Iterable[CapturedEvent]
    ) -> IntegrationReport:
        expected = tuple(expected_ids)
        records = self.decode(events)
        received = tuple(str(x["record_id"]) for x in records)
        expected_set = set(expected)
        received_set = set(received)
        duplicates = len(received) - len(received_set)
        positions = {value: index for index, value in enumerate(expected)}
        ordered = all(
            positions.get(a, -1) <= positions.get(b, -1) for a, b in itertools.pairwise(received)
        )
        missing = tuple(sorted(expected_set - received_set))
        unexpected = tuple(sorted(received_set - expected_set))
        valid = (
            len(received) == len(expected)
            and duplicates == 0
            and not missing
            and not unexpected
            and ordered
        )
        return IntegrationReport(
            len(expected), len(received), duplicates, missing, unexpected, ordered, valid
        )


def encode_record(
    record_id: str, signal: str, *, trace_id: str, attributes: Mapping[str, Any] | None = None
) -> bytes:
    return json.dumps(
        {
            "record_id": record_id,
            "signal": signal,
            "trace_id": trace_id,
            "attributes": dict(attributes or {}),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
