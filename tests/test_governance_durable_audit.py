from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import aae_observability


def record(i=0, verdict="allow", outcome="decision", policy="p", rule="r"):
    return aae_observability.GovernanceAuditRecord(
        verdict, outcome, "agent.run", "generic", f"{rule}{i}" if rule else None, policy, 1.0 + i
    )


def test_jsonl_schema_flush_close_and_idempotence(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    sink = aae_observability.JsonLinesGovernanceAuditSink(path, flush_every=2)
    sink.emit(record())
    sink.emit(record(1))
    assert sink.flush()
    sink.close()
    sink.close()
    lines = [json.loads(x) for x in path.read_text().splitlines()]
    assert (
        len(lines) == 2
        and lines[0]["schema_version"] == "aae-observability.audit/v1"
        and sink.stats().closed
    )


def test_concurrent_writes_are_complete_json_lines(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    sink = aae_observability.JsonLinesGovernanceAuditSink(path, flush_every=50)
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(lambda i: sink.emit(record(i)), range(300)))
    sink.close()
    lines = path.read_text().splitlines()
    assert len(lines) == 300 and all(json.loads(x)["operation"] == "agent.run" for x in lines)


def test_bounded_rotation(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    sink = aae_observability.JsonLinesGovernanceAuditSink(path, max_bytes=400, rotation_count=2)
    for i in range(20):
        sink.emit(record(i))
    sink.close()
    assert sink.stats().rotations > 0 and path.exists() and path.with_name("audit.jsonl.1").exists()
    assert not path.with_name("audit.jsonl.3").exists()


def test_export_failure_does_not_change_allow_or_deny():
    class Broken:
        def emit(self, record):
            raise OSError("disk secret")

    class Engine:
        def __init__(self, v):
            self.v = v

        def evaluate(self, s):
            return aae_observability.PolicyResult(self.v)

    aae_observability.configure(
        policy_engine=Engine(aae_observability.Verdict.ALLOW), governance_audit_sink=Broken()
    )

    @aae_observability.instrument
    def allowed():
        return "ok"

    assert allowed() == "ok"
    aae_observability.configure(
        policy_engine=Engine(aae_observability.Verdict.DENY), governance_audit_sink=Broken()
    )

    @aae_observability.instrument
    def denied():
        return "bad"

    with pytest.raises(aae_observability.GovernanceDeniedError):
        denied()


def test_report_aggregation_and_immutability():
    report = aae_observability.GovernanceReport(aggregate_by_rule=True, max_distinct_rules=2)
    for item in [
        record(),
        record(1, verdict="deny", outcome="error", policy="p2"),
        record(2, rule="x"),
    ]:
        report.emit(item)
    snap = report.snapshot()
    assert (
        snap.total == 3
        and snap.verdicts["allow"] == 2
        and snap.outcomes["error"] == 1
        and snap.maximum_duration_ms == 3.0
        and snap.dropped_dimensions == 1
    )
    with pytest.raises(TypeError):
        snap.verdicts["allow"] = 7


def test_composite_isolates_and_flushes(tmp_path: Path):
    class Broken:
        def emit(self, r):
            raise RuntimeError

    audit = aae_observability.JsonLinesGovernanceAuditSink(tmp_path / "a.jsonl")
    report = aae_observability.GovernanceReport()
    sink = aae_observability.CompositeGovernanceAuditSink(Broken(), audit, report)
    sink.emit(record())
    assert sink.failures == 1 and report.snapshot().total == 1
    assert sink.flush()
    sink.close()
    assert audit.stats().closed


def test_api_report_and_shutdown_closes_sink(tmp_path: Path):
    sink = aae_observability.JsonLinesGovernanceAuditSink(tmp_path / "audit.jsonl")
    aae_observability.configure(governance_audit_sink=sink)

    @aae_observability.instrument
    def run():
        return 1

    assert run() == 1 and aae_observability.get_governance_report().snapshot().total == 1
    aae_observability.shutdown()
    assert sink.stats().closed
