from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from typing import Any

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import aae_observability
from aae_observability.config import DropPolicy


def env(
    v: Any, s: aae_observability.SignalType = aae_observability.SignalType.SPAN
) -> aae_observability.TelemetryEnvelope:
    return aae_observability.TelemetryEnvelope(s, v)


def test_envelope():
    e = env("x")
    assert e.signal_type is aae_observability.SignalType.SPAN and e.timestamp_ns > 0
    with pytest.raises(FrozenInstanceError):
        e.payload = "y"


def test_drop_oldest():
    b = aae_observability.TelemetryBuffer(3, DropPolicy.DROP_OLDEST)
    assert all(b.offer(env(i)) for i in range(5))
    assert [x.payload for x in b.drain()] == [2, 3, 4]
    s = b.stats()
    assert s.dropped_oldest == 2 and s.high_water_mark == 3


def test_drop_new():
    b = aae_observability.TelemetryBuffer(2, DropPolicy.DROP_NEW)
    assert b.offer(env(1)) and b.offer(env(2)) and not b.offer(env(3))
    assert [x.payload for x in b.drain()] == [1, 2]
    assert b.stats().dropped_new == 1


def test_contention():
    b = aae_observability.TelemetryBuffer(2)
    assert b._lock.acquire()
    try:
        assert not b.offer(env("x"))
    finally:
        b._lock.release()
    assert b.stats().lock_contention_drops == 1


def test_drain_close():
    b = aae_observability.TelemetryBuffer(5)
    b.offer_many(env(i) for i in range(5))
    assert [x.payload for x in b.drain(2)] == [0, 1]
    b.close()
    assert not b.offer(env(9))
    assert [x.payload for x in b.drain()] == [2, 3, 4]


def test_concurrency():
    attempts = 4000
    b = aae_observability.TelemetryBuffer(128)
    with ThreadPoolExecutor(max_workers=16) as p:
        r = list(p.map(lambda i: b.offer(env(i)), range(attempts)))
    s = b.stats()
    assert (
        s.current_size <= 128
        and s.total_accepted == sum(r)
        and s.total_accepted + s.lock_contention_drops == attempts
    )


def test_sink_and_flush():
    received = []
    sink = aae_observability.BufferedTelemetrySink(
        aae_observability.TelemetryBuffer(10),
        drain_handler=lambda batch: received.extend(batch) or True,
    )
    sink.emit(spans=["s"], metrics=["m"], logs=["l"])
    assert sink.force_flush()
    assert [x.signal_type for x in received] == [
        aae_observability.SignalType.SPAN,
        aae_observability.SignalType.METRIC,
        aae_observability.SignalType.LOG,
    ]


def test_failed_flush_requeues():
    sink = aae_observability.BufferedTelemetrySink(
        aae_observability.TelemetryBuffer(2), drain_handler=lambda batch: False
    )
    sink.emit(spans=[1, 2])
    assert not sink.force_flush()
    assert [x.payload for x in sink.buffer.drain()] == [1, 2]


def test_self_metrics():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics = aae_observability.BufferMetrics.create(provider.get_meter("t"))
    sink = aae_observability.BufferedTelemetrySink(
        aae_observability.TelemetryBuffer(1, DropPolicy.DROP_NEW), buffer_metrics=metrics
    )
    sink.emit(spans=[1, 2])
    names = {
        m.name
        for r in reader.get_metrics_data().resource_metrics
        for s in r.scope_metrics
        for m in s.metrics
    }
    assert {
        "aae.observability.telemetry.buffer.dropped",
        "aae.observability.telemetry.buffer.utilization",
    }.issubset(names)


def test_default_config():
    aae_observability.configure(
        aae_observability.TelemetryConfig(buffer_capacity=7, max_batch_size=7)
    )
    from aae_observability.api import _STATE

    assert (
        isinstance(_STATE.telemetry_sink, aae_observability.BufferedTelemetrySink)
        and _STATE.telemetry_buffer.capacity == 7
    )
