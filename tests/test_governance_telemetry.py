import time

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import aae_observability


class E:
    def __init__(self, r):
        self.r = r

    def evaluate(self, s):
        return self.r


def names(r):
    return {
        m.name
        for x in r.get_metrics_data().resource_metrics
        for y in x.scope_metrics
        for m in y.metrics
    }


def setup(e, a=None, g=None):
    r = InMemoryMetricReader()
    aae_observability.configure(
        governance=g,
        policy_engine=e,
        meter_provider=MeterProvider(metric_readers=[r]),
        governance_audit_sink=a,
    )
    return r


def test_allow_metrics_audit():
    a = aae_observability.InMemoryGovernanceAuditSink()
    r = setup(
        E(
            aae_observability.PolicyResult(
                aae_observability.Verdict.ALLOW, rule_id="r", metadata={"policy": "p"}
            )
        ),
        a,
    )

    @aae_observability.instrument
    def f():
        return 1

    assert (
        f() == 1
        and {
            "aae.observability.governance.decisions",
            "aae.observability.governance.duration",
        }.issubset(names(r))
        and a.records[0].policy_name == "p"
    )


def test_deny_audit():
    a = aae_observability.InMemoryGovernanceAuditSink()
    setup(E(aae_observability.PolicyResult(aae_observability.Verdict.DENY, rule_id="d")), a)

    @aae_observability.instrument
    def f():
        return 1

    with pytest.raises(aae_observability.GovernanceDeniedError):
        f()
    assert a.records[0].rule_id == "d"


def test_timeout_metric():
    class S:
        def evaluate(self, s):
            time.sleep(0.05)
            return aae_observability.PolicyResult()

    r = setup(S(), g=aae_observability.GovernanceConfig(evaluation_timeout_ms=1))

    @aae_observability.instrument
    def f():
        return 1

    with pytest.raises(aae_observability.GovernanceTimeoutError):
        f()
    assert "aae.observability.governance.timeouts" in names(r)


def test_audit_disabled():
    a = aae_observability.InMemoryGovernanceAuditSink()
    setup(
        E(aae_observability.PolicyResult()),
        a,
        aae_observability.GovernanceConfig(audit_enabled=False),
    )

    @aae_observability.instrument
    def f():
        return 1

    assert f() == 1 and not a.records


def test_audit_safe():
    a = aae_observability.InMemoryGovernanceAuditSink()
    setup(E(aae_observability.PolicyResult(aae_observability.Verdict.ALLOW, "secret reason")), a)

    @aae_observability.instrument
    def f(secret):
        return secret

    assert (
        f("private") == "private"
        and "private" not in repr(a.records[0])
        and "secret reason" not in repr(a.records[0])
    )
