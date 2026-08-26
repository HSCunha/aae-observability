"""Tests for Release 0.2.2 semantic operations, metrics, and data controls."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import aae_observability
from aae_observability import semconv


def providers() -> tuple[TracerProvider, InMemorySpanExporter, MeterProvider, InMemoryMetricReader]:
    spans = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(spans))
    metric_reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[metric_reader])
    return tracer_provider, spans, meter_provider, metric_reader


def metric_points(reader: InMemoryMetricReader) -> dict[str, list[Any]]:
    data = reader.get_metrics_data()
    result: dict[str, list[Any]] = {}
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                result.setdefault(metric.name, []).extend(metric.data.data_points)
    return result


def test_formal_operation_types_create_expected_hierarchy() -> None:
    tracer, spans, meter, _ = providers()
    aae_observability.configure(tracer_provider=tracer, meter_provider=meter)

    @aae_observability.instrument(
        agent_name="retriever", operation=aae_observability.OperationType.RETRIEVAL_QUERY
    )
    def retrieve() -> str:
        return "context"

    @aae_observability.instrument(
        agent_name="planner", operation=aae_observability.OperationType.LLM_CHAT
    )
    def chat() -> str:
        return retrieve()

    @aae_observability.instrument(
        agent_name="orchestrator", operation=aae_observability.OperationType.AGENT_RUN
    )
    def run() -> str:
        return chat()

    assert run() == "context"
    by_name = {span.name: span for span in spans.get_finished_spans()}
    parent = by_name["agent.run orchestrator"]
    child = by_name["llm.chat planner"]
    grandchild = by_name["retrieval.query retriever"]
    assert child.parent.span_id == parent.context.span_id
    assert grandchild.parent.span_id == child.context.span_id
    assert parent.attributes[semconv.GEN_AI_OPERATION_NAME] == "agent.run"
    assert child.attributes[semconv.GEN_AI_OPERATION_NAME] == "llm.chat"
    assert grandchild.attributes[semconv.GEN_AI_OPERATION_NAME] == "retrieval.query"


def test_metrics_cover_success_error_duration_and_active_balance() -> None:
    tracer, _, meter, reader = providers()
    aae_observability.configure(tracer_provider=tracer, meter_provider=meter)

    @aae_observability.instrument(agent_name="successful")
    def success() -> str:
        return "ok"

    @aae_observability.instrument(agent_name="failing")
    def fail() -> None:
        raise RuntimeError("failure")

    assert success() == "ok"
    with pytest.raises(RuntimeError):
        fail()

    points = metric_points(reader)
    assert sum(point.value for point in points["aae.observability.operation.invocations"]) == 2
    assert sum(point.value for point in points["aae.observability.operation.errors"]) == 1
    assert sum(point.value for point in points["aae.observability.operation.active"]) == 0
    assert sum(point.count for point in points["aae.observability.operation.duration"]) == 2
    all_attributes = [point.attributes for values in points.values() for point in values]
    assert all("gen_ai.agent.name" not in attrs for attrs in all_attributes)
    assert all(
        "aae.observability.output" not in attrs and "aae.observability.input" not in attrs
        for attrs in all_attributes
    )


def test_adapter_supplied_token_usage_is_recorded() -> None:
    tracer, _, meter, reader = providers()

    class TokenAdapter(aae_observability.BaseFrameworkAdapter):
        framework = aae_observability.Framework.GENERIC

        def matches(self, func: Any) -> bool:
            return True

        def extract_context(
            self, func: Any, args: tuple[Any, ...], kwargs: Mapping[str, Any]
        ) -> aae_observability.AgentCall:
            return aae_observability.AgentCall(
                agent_name="model",
                operation=aae_observability.OperationType.LLM_CHAT,
                function_name=func.__name__,
                inputs=args,
                kwargs=kwargs,
                attributes={
                    "gen_ai.usage.input_tokens": 12,
                    "gen_ai.usage.output_tokens": 5,
                },
            )

    aae_observability.configure(
        tracer_provider=tracer,
        meter_provider=meter,
        adapters=(TokenAdapter(),),
    )

    @aae_observability.instrument(agent_name="model")
    def invoke() -> str:
        return "done"

    invoke()
    points = metric_points(reader)
    assert sum(p.value for p in points["gen_ai.client.token.usage.input"]) == 12
    assert sum(p.value for p in points["gen_ai.client.token.usage.output"]) == 5


def test_sensitive_data_is_disabled_by_default() -> None:
    tracer, spans, meter, _ = providers()
    aae_observability.configure(tracer_provider=tracer, meter_provider=meter)

    @aae_observability.instrument(agent_name="private")
    def process(secret: str) -> str:
        return f"result:{secret}"

    process("do-not-record")
    span = spans.get_finished_spans()[0]
    text = repr(span.events) + repr(span.attributes)
    assert "do-not-record" not in text
    assert not any(event.name.startswith("aae.observability.sensitive") for event in span.events)


def test_sensitive_data_opt_in_redacts_and_truncates() -> None:
    tracer, spans, meter, _ = providers()
    telemetry = aae_observability.TelemetryConfig(
        capture_sensitive_data=True,
        sensitive_data_max_length=64,
    )
    aae_observability.configure(
        telemetry,
        tracer_provider=tracer,
        meter_provider=meter,
        sensitive_data_redactor=lambda value: value.replace("secret", "[REDACTED]"),
    )

    @aae_observability.instrument(agent_name="private")
    def process(value: str) -> str:
        return "secret-output-" + ("x" * 100)

    process("secret-input-" + ("y" * 100))
    events = {event.name: event for event in spans.get_finished_spans()[0].events}
    input_value = events["aae.observability.sensitive.input"].attributes["aae.observability.input"]
    output_value = events["aae.observability.sensitive.output"].attributes[
        "aae.observability.output"
    ]
    assert "secret" not in input_value.lower()
    assert "secret" not in output_value.lower()
    assert "[REDACTED]" in input_value
    assert len(input_value) <= 64
    assert len(output_value) <= 64


def test_duplicate_instrumentation_returns_same_wrapper_and_one_span() -> None:
    tracer, spans, meter, _ = providers()
    aae_observability.configure(tracer_provider=tracer, meter_provider=meter)

    @aae_observability.instrument(agent_name="once")
    def run() -> str:
        return "ok"

    decorated_again = aae_observability.instrument(run, agent_name="twice")
    assert decorated_again is run
    assert decorated_again() == "ok"
    assert len(spans.get_finished_spans()) == 1
    assert spans.get_finished_spans()[0].attributes[semconv.GEN_AI_AGENT_NAME] == "once"


def test_sampling_ratio_controls_private_tracer_provider() -> None:
    # A zero ratio produces non-recording root spans when aae_observability owns the provider.
    telemetry = aae_observability.TelemetryConfig(sampling_ratio=0.0)
    aae_observability.configure(telemetry)

    @aae_observability.instrument(agent_name="unsampled")
    def run() -> str:
        return "ok"

    assert run() == "ok"
    # Validate the configured private provider's sampler instead of requiring
    # access to private span processors/exporters.
    from aae_observability.api import _STATE

    decision = _STATE.tracer_provider.sampler.should_sample(  # type: ignore[union-attr]
        parent_context=None,
        trace_id=1,
        name="agent.run unsampled",
    )
    assert decision.decision.is_sampled() is False
