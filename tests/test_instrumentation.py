"""Tests for the Release 0.2.0 synchronous instrumentation pipeline."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

import aae_observability
from aae_observability import semconv


def tracing_provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    """Create an isolated provider/exporter pair for deterministic tests."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def test_successful_tool_call_creates_genai_span() -> None:
    provider, exporter = tracing_provider()
    aae_observability.configure(tracer_provider=provider)

    @aae_observability.instrument(agent_name="planner", tool_name="search")
    def search(query: str, limit: int = 1) -> list[str]:
        return [query] * limit

    assert search("tea", 2) == ["tea", "tea"]
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "tool.call search"
    assert span.status.status_code is StatusCode.OK
    assert span.attributes[semconv.GEN_AI_OPERATION_NAME] == "tool.call"
    assert span.attributes[semconv.GEN_AI_AGENT_NAME] == "planner"
    assert span.attributes[semconv.GEN_AI_TOOL_NAME] == "search"
    assert span.attributes["code.function.name"] == "search"
    assert span.attributes["aae.observability.framework"] == "generic"
    assert [event.name for event in span.events] == [
        "aae.observability.interceptor.pre_invocation",
        "aae.observability.interceptor.post_invocation",
    ]


def test_agent_call_without_tool_uses_invoke_agent_operation() -> None:
    provider, exporter = tracing_provider()
    aae_observability.configure(tracer_provider=provider)

    @aae_observability.instrument(agent_name="summarizer")
    def summarize(text: str) -> str:
        return text.upper()

    assert summarize("hello") == "HELLO"
    span = exporter.get_finished_spans()[0]
    assert span.name == "agent.run summarizer"
    assert span.attributes[semconv.GEN_AI_OPERATION_NAME] == "agent.run"
    assert semconv.GEN_AI_TOOL_NAME not in span.attributes


def test_exception_is_recorded_and_original_exception_is_reraised() -> None:
    provider, exporter = tracing_provider()
    aae_observability.configure(tracer_provider=provider)

    error = RuntimeError("agent failed")

    @aae_observability.instrument(agent_name="planner")
    def fail() -> None:
        raise error

    with pytest.raises(RuntimeError) as caught:
        fail()
    assert caught.value is error

    span = exporter.get_finished_spans()[0]
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description == "agent failed"
    exception_events = [event for event in span.events if event.name == "exception"]
    assert len(exception_events) == 1
    assert exception_events[0].attributes["exception.type"] == "RuntimeError"
    assert exception_events[0].attributes["exception.message"] == "agent failed"


def test_wrapper_preserves_metadata_signature_and_return_identity() -> None:
    provider, _ = tracing_provider()
    aae_observability.configure(tracer_provider=provider)
    expected = object()

    @aae_observability.instrument(agent_name="identity")
    def identity(value: object, optional: str = "x") -> object:
        """Return the input."""
        del optional
        return value

    assert identity(expected) is expected
    assert identity.__name__ == "identity"
    assert identity.__doc__ == "Return the input."
    assert list(inspect.signature(identity).parameters) == ["value", "optional"]


def test_pre_and_post_hooks_receive_normalized_call_and_span() -> None:
    provider, exporter = tracing_provider()
    observed: list[tuple[str, Any]] = []

    def pre_hook(call: aae_observability.AgentCall, span: Any) -> None:
        observed.append(("pre", call.tool_name))
        span.set_attribute("test.pre_hook", True)

    def post_hook(
        call: aae_observability.AgentCall,
        span: Any,
        result: Any | None,
        error: BaseException | None,
    ) -> None:
        observed.append(("post", result))
        assert call.agent_name == "planner"
        assert error is None
        span.set_attribute("test.post_hook", True)

    aae_observability.configure(
        tracer_provider=provider,
        pre_hooks=(pre_hook,),
        post_hooks=(post_hook,),
    )

    @aae_observability.instrument(agent_name="planner", tool_name="calculate")
    def calculate(value: int) -> int:
        return value * 2

    assert calculate(4) == 8
    assert observed == [("pre", "calculate"), ("post", 8)]
    span = exporter.get_finished_spans()[0]
    assert span.attributes["test.pre_hook"] is True
    assert span.attributes["test.post_hook"] is True


def test_custom_adapter_is_selected_before_generic_fallback() -> None:
    provider, exporter = tracing_provider()

    class CustomAdapter(aae_observability.BaseFrameworkAdapter):
        framework = aae_observability.Framework.LANGCHAIN

        def matches(self, func: Any) -> bool:
            return bool(getattr(func, "custom_agent", False))

        def extract_context(
            self,
            func: Any,
            args: tuple[Any, ...],
            kwargs: Mapping[str, Any],
        ) -> aae_observability.AgentCall:
            return aae_observability.AgentCall(
                agent_name="custom-planner",
                operation="custom_operation",
                framework=self.framework,
                function_name=func.__name__,
                inputs=args,
                kwargs=dict(kwargs),
            )

    def target(value: int) -> int:
        return value + 1

    target.custom_agent = True
    decorated = aae_observability.instrument(target)
    aae_observability.configure(
        tracer_provider=provider,
        adapters=(CustomAdapter(), aae_observability.GenericFrameworkAdapter()),
    )

    assert decorated(1) == 2
    span = exporter.get_finished_spans()[0]
    assert span.name == "custom_operation custom-planner"
    assert span.attributes["aae.observability.framework"] == "langchain"
    assert span.attributes[semconv.GEN_AI_OPERATION_NAME] == "custom_operation"


def test_parent_context_is_propagated_for_nested_instrumented_calls() -> None:
    provider, exporter = tracing_provider()
    aae_observability.configure(tracer_provider=provider)

    @aae_observability.instrument(agent_name="worker", tool_name="work")
    def worker() -> str:
        return "done"

    @aae_observability.instrument(agent_name="orchestrator")
    def orchestrator() -> str:
        return worker()

    assert orchestrator() == "done"
    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert spans["tool.call work"].parent.span_id == spans["agent.run orchestrator"].context.span_id


def test_hook_failure_does_not_change_application_behavior() -> None:
    provider, exporter = tracing_provider()

    def broken_pre_hook(call: aae_observability.AgentCall, span: Any) -> None:
        del call, span
        raise RuntimeError("hook failed")

    def broken_post_hook(
        call: aae_observability.AgentCall,
        span: Any,
        result: Any | None,
        error: BaseException | None,
    ) -> None:
        del call, span, result, error
        raise RuntimeError("hook failed")

    aae_observability.configure(
        tracer_provider=provider,
        pre_hooks=(broken_pre_hook,),
        post_hooks=(broken_post_hook,),
    )

    @aae_observability.instrument(agent_name="resilient")
    def run() -> str:
        return "application result"

    assert run() == "application result"
    span = exporter.get_finished_spans()[0]
    hook_errors = [event for event in span.events if event.name == "aae.observability.hook.error"]
    assert len(hook_errors) == 2
    assert {event.attributes["aae.observability.hook.phase"] for event in hook_errors} == {
        "pre_invocation",
        "post_invocation",
    }
