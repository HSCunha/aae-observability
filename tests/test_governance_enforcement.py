from __future__ import annotations

import asyncio
import time

import pytest

import aae_observability


class Engine:
    def __init__(self, result):
        self.result = result
        self.calls = 0
        self.snapshots = []

    def evaluate(self, snapshot):
        self.calls += 1
        self.snapshots.append(snapshot)
        return self.result


def test_allow_and_snapshot():
    e = Engine(aae_observability.PolicyResult(aae_observability.Verdict.ALLOW))
    aae_observability.configure(policy_engine=e)

    @aae_observability.instrument(agent_name="planner")
    def run():
        return 7

    assert run() == 7 and e.snapshots[0].call.agent_name == "planner"


def test_deny_prevents_sync_body():
    e = Engine(
        aae_observability.PolicyResult(aae_observability.Verdict.DENY, "blocked", rule_id="r1")
    )
    ran = []
    aae_observability.configure(policy_engine=e)

    @aae_observability.instrument
    def run():
        ran.append(1)

    with pytest.raises(aae_observability.GovernanceDeniedError) as x:
        run()
    assert ran == [] and x.value.result.rule_id == "r1"


@pytest.mark.parametrize(
    "verdict",
    [
        aae_observability.Verdict.REQUIRE_APPROVAL,
        aae_observability.Verdict.REDACT,
        aae_observability.Verdict.KILL,
    ],
)
def test_non_allow_verdicts_block(verdict):
    aae_observability.configure(policy_engine=Engine(aae_observability.PolicyResult(verdict)))

    @aae_observability.instrument
    def run():
        return 1

    with pytest.raises(aae_observability.GovernanceDeniedError):
        run()


def test_fail_open_error():
    class Bad:
        def evaluate(self, s):
            raise RuntimeError("sensitive")

    aae_observability.configure(
        governance=aae_observability.GovernanceConfig(fail_closed=False), policy_engine=Bad()
    )

    @aae_observability.instrument
    def run():
        return "ok"

    assert run() == "ok"


def test_fail_closed_error_safe():
    class Bad:
        def evaluate(self, s):
            raise RuntimeError("sensitive")

    aae_observability.configure(policy_engine=Bad())

    @aae_observability.instrument
    def run():
        return 1

    with pytest.raises(aae_observability.GovernanceEvaluationError) as x:
        run()
    assert str(x.value) == "governance evaluation failed"


def test_caller_bounded_sync_timeout():
    class Slow:
        def evaluate(self, s):
            time.sleep(0.2)
            return aae_observability.PolicyResult()

    aae_observability.configure(
        governance=aae_observability.GovernanceConfig(evaluation_timeout_ms=5), policy_engine=Slow()
    )

    @aae_observability.instrument
    def run():
        raise AssertionError

    started = time.monotonic()
    with pytest.raises(aae_observability.GovernanceTimeoutError):
        run()
    assert time.monotonic() - started < 0.1


def test_timeout_fail_open():
    class Slow:
        def evaluate(self, s):
            time.sleep(0.05)
            return aae_observability.PolicyResult(aae_observability.Verdict.DENY)

    aae_observability.configure(
        governance=aae_observability.GovernanceConfig(fail_closed=False, evaluation_timeout_ms=1),
        policy_engine=Slow(),
    )

    @aae_observability.instrument
    def run():
        return "ok"

    assert run() == "ok"


def test_async_engine_denies_before_body():
    ran = []

    class AsyncEngine:
        async def evaluate(self, s):
            await asyncio.sleep(0)
            return aae_observability.PolicyResult(aae_observability.Verdict.DENY)

    aae_observability.configure(policy_engine=AsyncEngine())

    @aae_observability.instrument
    async def run():
        ran.append(1)

    with pytest.raises(aae_observability.GovernanceDeniedError):
        asyncio.run(run())
    assert ran == []


def test_async_timeout_fail_open():
    class Slow:
        async def evaluate(self, s):
            await asyncio.sleep(0.05)
            return aae_observability.PolicyResult(aae_observability.Verdict.DENY)

    aae_observability.configure(
        governance=aae_observability.GovernanceConfig(fail_closed=False, evaluation_timeout_ms=1),
        policy_engine=Slow(),
    )

    @aae_observability.instrument
    async def run():
        return "ok"

    assert asyncio.run(run()) == "ok"


def test_generator_denied_before_body():
    ran = []
    aae_observability.configure(
        policy_engine=Engine(aae_observability.PolicyResult(aae_observability.Verdict.DENY))
    )

    @aae_observability.instrument
    def stream():
        ran.append(1)
        yield 1

    with pytest.raises(aae_observability.GovernanceDeniedError):
        next(stream())
    assert ran == []


def test_async_generator_denied_before_body():
    ran = []
    aae_observability.configure(
        policy_engine=Engine(aae_observability.PolicyResult(aae_observability.Verdict.DENY))
    )

    @aae_observability.instrument
    async def stream():
        ran.append(1)
        yield 1

    async def consume():
        with pytest.raises(aae_observability.GovernanceDeniedError):
            await stream().__anext__()

    asyncio.run(consume())
    assert ran == []


def test_disabled_bypasses_engine():
    e = Engine(aae_observability.PolicyResult(aae_observability.Verdict.DENY))
    aae_observability.configure(
        governance=aae_observability.GovernanceConfig(enabled=False), policy_engine=e
    )

    @aae_observability.instrument
    def run():
        return "ok"

    assert run() == "ok" and e.calls == 0
