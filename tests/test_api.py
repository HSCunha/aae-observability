"""Tests for the Release 0.1.0 public API."""

import inspect

import aae_observability


def test_version() -> None:
    assert aae_observability.__version__ == "0.6.3"


def test_bare_decorator_is_transparent() -> None:
    @aae_observability.instrument
    def add(a: int, b: int = 1) -> int:
        """Add numbers."""
        return a + b

    assert add(2, 3) == 5
    assert add.__name__ == "add"
    assert add.__doc__ == "Add numbers."
    assert list(inspect.signature(add).parameters) == ["a", "b"]
    assert add.__aae_observability_instrumented__ is True


def test_parameterized_decorator_records_markers() -> None:
    @aae_observability.instrument(agent_name="planner", tool_name="search")
    def run(value: str) -> str:
        return value

    assert run("ok") == "ok"
    assert run.__aae_observability_agent_name__ == "planner"
    assert run.__aae_observability_tool_name__ == "search"


def test_configure_and_shutdown() -> None:
    aae_observability.configure(aae_observability.TelemetryConfig(service_name="test-agent"))
    assert aae_observability.is_configured() is True
    aae_observability.shutdown()
    assert aae_observability.is_configured() is False


def test_policy_result() -> None:
    assert aae_observability.PolicyResult().allowed is True
    assert aae_observability.PolicyResult(aae_observability.Verdict.DENY).allowed is False
