from collections.abc import Callable, Mapping
from typing import Any

from aae_observability.adapters.common import (
    attribute_or_mapping,
    first_value,
    normalize_identifier,
)
from aae_observability.contracts import AgentCall, BaseFrameworkAdapter, Framework, OperationType


class MultiAgentAdapter(BaseFrameworkAdapter):
    framework = Framework.MULTI_AGENT

    def matches(self, func: Callable[..., Any]) -> bool:
        return bool(
            getattr(func, "__aae_observability_multiagent__", False)
            or getattr(func, "__aae_observability_handoff__", False)
        )

    def extract_context(
        self, func: Callable[..., Any], args: tuple[Any, ...], kwargs: Mapping[str, Any]
    ) -> AgentCall:
        context = first_value(kwargs.get("handoff"), kwargs.get("context"), {})
        source = first_value(
            kwargs.get("source_agent"), attribute_or_mapping(context, "source_agent")
        )
        target = first_value(
            kwargs.get("target_agent"),
            attribute_or_mapping(context, "target_agent"),
            getattr(func, "__aae_observability_agent_name__", None),
        )
        correlation = first_value(
            kwargs.get("correlation_id"), attribute_or_mapping(context, "correlation_id")
        )
        attrs = {}
        if source:
            attrs["aae.observability.handoff.source_agent"] = str(source)
        if target:
            attrs["aae.observability.handoff.target_agent"] = str(target)
        if correlation:
            attrs["aae.observability.correlation.id"] = str(correlation)
        return AgentCall(
            agent_name=normalize_identifier(target),
            operation=OperationType.AGENT_HANDOFF,
            framework=self.framework,
            function_name=getattr(func, "__name__", None),
            inputs=args,
            kwargs=dict(kwargs),
            run_id=normalize_identifier(
                first_value(
                    kwargs.get("run_id"), attribute_or_mapping(context, "run_id"), correlation
                )
            ),
            trace_id=normalize_identifier(
                first_value(kwargs.get("trace_id"), attribute_or_mapping(context, "trace_id"))
            ),
            parent_span_id=normalize_identifier(
                first_value(
                    kwargs.get("parent_span_id"), attribute_or_mapping(context, "parent_span_id")
                )
            ),
            attributes=attrs,
        )
