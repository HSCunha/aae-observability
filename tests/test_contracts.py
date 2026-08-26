"""Tests for the Release 0.1.1 extension-point contracts."""

from collections.abc import Mapping
from typing import Any

import aae_observability


def test_reference_implementations_satisfy_runtime_protocols() -> None:
    assert isinstance(aae_observability.AllowAllPolicyEngine(), aae_observability.PolicyEngine)
    assert isinstance(aae_observability.DenyAllPolicyEngine(), aae_observability.PolicyEngine)
    assert isinstance(aae_observability.NullTelemetrySink(), aae_observability.TelemetrySink)
    assert isinstance(
        aae_observability.GenericFrameworkAdapter(), aae_observability.FrameworkAdapter
    )


def test_policy_engines_return_expected_verdicts() -> None:
    snapshot = aae_observability.ActionSnapshot(aae_observability.AgentCall(agent_name="planner"))
    assert (
        aae_observability.AllowAllPolicyEngine().evaluate(snapshot).verdict
        is aae_observability.Verdict.ALLOW
    )
    assert (
        aae_observability.DenyAllPolicyEngine().evaluate(snapshot).verdict
        is aae_observability.Verdict.DENY
    )


def test_action_snapshot_composes_identity_call_and_context() -> None:
    snapshot = aae_observability.ActionSnapshot(
        call=aae_observability.AgentCall(agent_name="planner", tool_name="search"),
        identity=aae_observability.Identity(principal_id="user-1", roles=("operator",)),
        context={"environment": "test"},
    )
    assert snapshot.call.is_tool_call is True
    assert snapshot.identity.roles == ("operator",)
    assert snapshot.context["environment"] == "test"


def test_generic_adapter_normalizes_decorator_markers() -> None:
    @aae_observability.instrument(agent_name="planner", tool_name="search")
    def run(query: str, *, limit: int = 1) -> str:
        return query * limit

    adapter = aae_observability.GenericFrameworkAdapter()
    call = adapter.extract_context(run, ("q",), {"limit": 2})
    assert adapter.matches(run) is True
    assert call.agent_name == "planner"
    assert call.tool_name == "search"
    assert call.function_name == "run"
    assert call.inputs == ("q",)
    assert call.kwargs == {"limit": 2}
    assert call.framework is aae_observability.Framework.GENERIC


def test_custom_adapter_can_implement_the_abc() -> None:
    class CustomAdapter(aae_observability.BaseFrameworkAdapter):
        framework = aae_observability.Framework.LANGCHAIN

        def matches(self, func: Any) -> bool:
            return bool(getattr(func, "is_chain", False))

        def extract_context(
            self,
            func: Any,
            args: tuple[Any, ...],
            kwargs: Mapping[str, Any],
        ) -> aae_observability.AgentCall:
            return aae_observability.AgentCall(
                framework=self.framework,
                function_name=func.__name__,
                inputs=args,
                kwargs=dict(kwargs),
            )

    def chain() -> None:
        return None

    chain.is_chain = True
    adapter = CustomAdapter()
    assert isinstance(adapter, aae_observability.FrameworkAdapter)
    assert adapter.matches(chain) is True
    assert adapter.extract_context(chain, (), {}).framework is aae_observability.Framework.LANGCHAIN


def test_null_telemetry_sink_counts_and_lifecycle() -> None:
    sink = aae_observability.NullTelemetrySink()
    sink.emit(spans=[1, 2], metrics=[3], logs=[4, 5, 6])
    assert sink.emitted_spans == 2
    assert sink.emitted_metrics == 1
    assert sink.emitted_logs == 3
    assert sink.force_flush() is True
    sink.shutdown()
    assert sink.flush_count == 1
    assert sink.shutdown_called is True


def test_configure_wires_custom_contracts_and_shutdown() -> None:
    sink = aae_observability.NullTelemetrySink()
    aae_observability.configure(
        policy_engine=aae_observability.DenyAllPolicyEngine(),
        telemetry_sink=sink,
    )
    assert aae_observability.is_configured() is True
    aae_observability.shutdown()
    assert sink.flush_count == 1
    assert sink.shutdown_called is True
