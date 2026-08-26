from collections.abc import Mapping
from typing import Any

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import aae_observability
from aae_observability.adapters import registry


def test_default_order_and_explicit_fallback():
    assert [type(a).__name__ for a in aae_observability.default_adapters()] == [
        "MultiAgentAdapter",
        "MicrosoftAgentFrameworkAdapter",
        "LangChainAdapter",
        "GenericFrameworkAdapter",
    ]
    values = aae_observability.build_adapter_registry(
        (aae_observability.LangChainAdapter(),), discover_plugins=False
    )
    assert isinstance(values[0], aae_observability.LangChainAdapter) and isinstance(
        values[-1], aae_observability.GenericFrameworkAdapter
    )


def test_maf_normalization():
    def run():
        pass

    run.__aae_observability_maf__ = True
    a = aae_observability.MicrosoftAgentFrameworkAdapter()
    c = a.extract_context(
        run,
        (),
        {
            "context": {
                "agent_name": "maf",
                "agent_id": "7",
                "run_id": "42",
                "input_tokens": 12,
                "output_tokens": 8,
                "otel_source_name": "native",
            }
        },
    )
    assert (
        a.matches(run)
        and c.framework is aae_observability.Framework.MICROSOFT_AGENT_FRAMEWORK
        and c.operation is aae_observability.OperationType.AGENT_RUN
    )
    assert (
        c.agent_name == "maf"
        and c.attributes["gen_ai.usage.input_tokens"] == 12
        and c.attributes["aae.observability.maf.otel_source_name"] == "native"
    )


def test_langchain_types_and_tokens():
    a = aae_observability.LangChainAdapter()

    def model():
        pass

    model.__aae_observability_langchain__ = True
    model.__aae_observability_langchain_type__ = "chat_model"
    c = a.extract_context(
        model,
        (),
        {
            "run_id": "r",
            "parent_run_id": "p",
            "usage_metadata": {"input_tokens": 4, "output_tokens": 2},
        },
    )
    assert (
        a.matches(model)
        and c.operation is aae_observability.OperationType.LLM_CHAT
        and c.run_id == "r"
        and c.parent_span_id == "p"
    )
    assert c.attributes["gen_ai.usage.output_tokens"] == 2


def test_multiagent_handoff():
    def delegate():
        pass

    delegate.__aae_observability_handoff__ = True
    c = aae_observability.MultiAgentAdapter().extract_context(
        delegate,
        (),
        {"source_agent": "planner", "target_agent": "reviewer", "correlation_id": "corr"},
    )
    assert (
        c.operation is aae_observability.OperationType.AGENT_HANDOFF
        and c.agent_name == "reviewer"
        and c.run_id == "corr"
    )
    assert c.attributes["aae.observability.handoff.source_agent"] == "planner"


def test_optional_import_safety():
    assert isinstance(
        aae_observability.MicrosoftAgentFrameworkAdapter(), aae_observability.FrameworkAdapter
    )
    assert isinstance(aae_observability.LangChainAdapter(), aae_observability.FrameworkAdapter)


def test_plugin_discovery(monkeypatch: Any):
    class Plugin(aae_observability.BaseFrameworkAdapter):
        def matches(self, func: Any) -> bool:
            return False

        def extract_context(
            self, func: Any, args: tuple[Any, ...], kwargs: Mapping[str, Any]
        ) -> aae_observability.AgentCall:
            return aae_observability.AgentCall()

    class EP:
        name = "plugin"

        def load(self):
            return Plugin

    monkeypatch.setattr(registry, "_selected_entry_points", lambda: (EP(),))
    assert isinstance(registry.discover_adapters()[0], Plugin)


def test_native_marker_avoids_span():
    ex = InMemorySpanExporter()
    p = TracerProvider()
    p.add_span_processor(SimpleSpanProcessor(ex))
    aae_observability.configure(tracer_provider=p, meter_provider=MeterProvider())

    def native():
        return "ok"

    native.__aae_observability_native_instrumented__ = True
    assert (
        aae_observability.instrument(native) is native
        and native() == "ok"
        and ex.get_finished_spans() == ()
    )


def test_registry_emits_handoff_span():
    ex = InMemorySpanExporter()
    p = TracerProvider()
    p.add_span_processor(SimpleSpanProcessor(ex))
    aae_observability.configure(
        tracer_provider=p, meter_provider=MeterProvider(), discover_adapters=False
    )

    def handoff(**kwargs):
        return kwargs["target_agent"]

    handoff.__aae_observability_handoff__ = True
    wrapped = aae_observability.instrument(handoff)
    assert (
        wrapped(source_agent="planner", target_agent="reviewer", correlation_id="c") == "reviewer"
    )
    s = ex.get_finished_spans()[0]
    assert (
        s.name == "agent.handoff reviewer"
        and s.attributes["aae.observability.framework"] == "multi_agent"
    )
