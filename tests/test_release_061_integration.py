from __future__ import annotations

import os

import pytest

from aae_observability.testing import (
    ChaosEventHubProducer,
    FakeEventHubProducer,
    RoundTripVerifier,
    encode_record,
)


def test_round_trip_count_attributes_and_order():
    producer = FakeEventHubProducer()
    ids = [f"r-{i}" for i in range(20)]
    for record_id in ids:
        producer.send(
            encode_record(
                record_id,
                "span",
                trace_id="trace-1",
                attributes={"gen_ai.operation.name": "agent.run"},
            ),
            partition_key="trace-1",
        )
    records = RoundTripVerifier.decode(producer.snapshot())
    assert all(r["attributes"]["gen_ai.operation.name"] == "agent.run" for r in records)
    assert RoundTripVerifier().verify(ids, producer.snapshot()).valid


def test_reconciliation_detects_missing_duplicate_and_unexpected():
    producer = FakeEventHubProducer()
    for rid in ["a", "a", "c", "x"]:
        producer.send(encode_record(rid, "span", trace_id="t"), partition_key="t")
    report = RoundTripVerifier().verify(["a", "b", "c"], producer.snapshot())
    assert (
        not report.valid
        and report.duplicates == 1
        and report.missing_ids == ("b",)
        and report.unexpected_ids == ("x",)
    )


def test_transient_failure_retries_without_duplicate_delivery():
    delays = []
    producer = FakeEventHubProducer()
    chaos = ChaosEventHubProducer(
        producer, failures_before_success=2, max_retries=3, base_delay_ms=5, sleeper=delays.append
    )
    chaos.send(encode_record("r-1", "span", trace_id="t"), partition_key="t")
    assert (
        chaos.attempts == 3
        and chaos.retries == 2
        and len(producer.snapshot()) == 1
        and delays == [0.005, 0.01]
    )


def test_retry_exhaustion_does_not_emit_partial_record():
    producer = FakeEventHubProducer()
    chaos = ChaosEventHubProducer(
        producer, failures_before_success=5, max_retries=2, sleeper=lambda _: None
    )
    with pytest.raises(TimeoutError):
        chaos.send(encode_record("r-1", "span", trace_id="t"))
    assert chaos.attempts == 3 and producer.snapshot() == ()


def test_mixed_signal_round_trip():
    producer = FakeEventHubProducer()
    expected = []
    for i, signal in enumerate(["span", "metric", "log"] * 10):
        rid = f"r-{i:02d}"
        expected.append(rid)
        producer.send(encode_record(rid, signal, trace_id=f"t-{i // 3}"))
    decoded = RoundTripVerifier.decode(producer.snapshot())
    assert {x["signal"] for x in decoded} == {"span", "metric", "log"}
    assert RoundTripVerifier().verify(expected, producer.snapshot()).valid


@pytest.mark.integration
def test_live_event_hub_configuration_is_explicitly_opt_in():
    if os.getenv("AAE_OBSERVABILITY_RUN_LIVE_EVENTHUB_TESTS") != "1":
        pytest.skip("live Event Hub tests are opt-in")
    required = ["AAE_OBSERVABILITY_EVENTHUB_NAMESPACE", "AAE_OBSERVABILITY_EVENTHUB_NAME"]
    missing = [name for name in required if not os.getenv(name)]
    assert not missing, f"missing live integration settings: {missing}"
