from __future__ import annotations

import asyncio
import contextlib
import inspect
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass

from aae_observability.contracts import ActionSnapshot, Identity, PolicyEngine
from aae_observability.governance.audit import GovernanceAuditSink, build_audit_record
from aae_observability.governance.telemetry import GovernanceMetrics
from aae_observability.types import PolicyResult, Verdict


class GovernanceDeniedError(PermissionError):
    def __init__(self, result):
        self.result = result
        super().__init__(f"governance denied action: {result.verdict.value}")


class GovernanceEvaluationError(RuntimeError):
    pass


class GovernanceTimeoutError(GovernanceEvaluationError):
    pass


@dataclass(frozen=True, slots=True)
class GovernanceSettings:
    engine: PolicyEngine
    enabled: bool = True
    fail_closed: bool = True
    timeout_ms: int = 50
    audit_enabled: bool = True
    metrics: GovernanceMetrics | None = None
    audit_sink: GovernanceAuditSink | None = None


def build_snapshot(call):
    i = call.attributes.get("aae.observability.identity")
    return ActionSnapshot(call, i if isinstance(i, Identity) else Identity(), {})


def _record(call, result, outcome, started, s):
    d = time.perf_counter() - started
    op = getattr(call.operation, "value", call.operation) or (
        "tool.call" if call.tool_name else "agent.run"
    )
    a = {
        "aae.observability.governance.verdict": result.verdict.value,
        "aae.observability.governance.outcome": outcome,
        "gen_ai.operation.name": str(op),
        "aae.observability.framework": call.framework.value,
    }
    if s.metrics:
        s.metrics.decisions.add(1, a)
        s.metrics.duration.record(d, a)
        if outcome == "error":
            s.metrics.errors.add(1, {"aae.observability.governance.outcome": "error"})
        if outcome == "timeout":
            s.metrics.timeouts.add(1, {"aae.observability.governance.outcome": "timeout"})
    if s.audit_enabled and s.audit_sink:
        with contextlib.suppress(Exception):
            s.audit_sink.emit(build_audit_record(call, result, outcome, d * 1000))


def _finish(call, result, started, s):
    _record(call, result, "decision", started, s)
    if result.verdict is not Verdict.ALLOW:
        raise GovernanceDeniedError(result)
    return result


def evaluate_sync(call, s):
    started = time.perf_counter()
    if not s.enabled:
        return PolicyResult(Verdict.ALLOW, "governance disabled")
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aae_observability-governance")
    f = pool.submit(s.engine.evaluate, build_snapshot(call))
    try:
        v = f.result(s.timeout_ms / 1000)
        if inspect.isawaitable(v):
            raise GovernanceEvaluationError("async policy engine requires async invocation")
        return _finish(call, v, started, s)
    except GovernanceDeniedError:
        raise
    except FutureTimeout as e:
        v = PolicyResult(Verdict.DENY if s.fail_closed else Verdict.ALLOW, "policy timeout")
        _record(call, v, "timeout", started, s)
        if s.fail_closed:
            raise GovernanceTimeoutError("governance evaluation timed out") from e
        return v
    except Exception as e:
        v = PolicyResult(Verdict.DENY if s.fail_closed else Verdict.ALLOW, "policy error")
        _record(call, v, "error", started, s)
        if s.fail_closed:
            raise GovernanceEvaluationError("governance evaluation failed") from e
        return v
    finally:
        f.cancel()
        pool.shutdown(wait=False, cancel_futures=True)


async def evaluate_async(call, s):
    started = time.perf_counter()
    if not s.enabled:
        return PolicyResult(Verdict.ALLOW, "governance disabled")
    try:
        v = s.engine.evaluate(build_snapshot(call))
        if inspect.isawaitable(v):
            v = await asyncio.wait_for(v, s.timeout_ms / 1000)
        return _finish(call, v, started, s)
    except GovernanceDeniedError:
        raise
    except asyncio.TimeoutError as e:
        v = PolicyResult(Verdict.DENY if s.fail_closed else Verdict.ALLOW, "policy timeout")
        _record(call, v, "timeout", started, s)
        if s.fail_closed:
            raise GovernanceTimeoutError("governance evaluation timed out") from e
        return v
    except Exception as e:
        v = PolicyResult(Verdict.DENY if s.fail_closed else Verdict.ALLOW, "policy error")
        _record(call, v, "error", started, s)
        if s.fail_closed:
            raise GovernanceEvaluationError("governance evaluation failed") from e
        return v
