from collections.abc import Callable, Mapping
from typing import Any

from aae_observability.adapters.common import (
    attribute_or_mapping,
    class_name,
    first_value,
    module_name,
    normalize_identifier,
    token_attributes,
)
from aae_observability.contracts import AgentCall, BaseFrameworkAdapter, Framework, OperationType


class MicrosoftAgentFrameworkAdapter(BaseFrameworkAdapter):
    framework = Framework.MICROSOFT_AGENT_FRAMEWORK

    def matches(self, func: Callable[..., Any]) -> bool:
        module, name = module_name(func), class_name(func)
        return bool(
            getattr(func, "__aae_observability_maf__", False)
            or "agent_framework" in module
            or "microsoft.agents" in module
            or name in {"chatclientagent", "aiagent", "agenttool"}
        )

    def extract_context(
        self, func: Callable[..., Any], args: tuple[Any, ...], kwargs: Mapping[str, Any]
    ) -> AgentCall:
        owner = getattr(func, "__self__", None)
        context = first_value(kwargs.get("context"), kwargs.get("run_context"), owner)
        tool = first_value(
            getattr(func, "__aae_observability_tool_name__", None),
            attribute_or_mapping(context, "tool_name", "function_name"),
        )
        operation = first_value(
            getattr(func, "__aae_observability_operation__", None),
            attribute_or_mapping(context, "operation"),
            OperationType.TOOL_CALL if tool else OperationType.AGENT_RUN,
        )
        attrs: dict[str, Any] = token_attributes(
            kwargs.get("usage"), kwargs.get("response_metadata"), context
        )
        source = first_value(
            attribute_or_mapping(context, "otel_source_name", "source_name"),
            getattr(func, "__otel_source_name__", None),
        )
        if source:
            attrs["aae.observability.maf.otel_source_name"] = str(source)
        return AgentCall(
            agent_name=normalize_identifier(
                first_value(
                    getattr(func, "__aae_observability_agent_name__", None),
                    attribute_or_mapping(context, "agent_name", "name"),
                    attribute_or_mapping(owner, "name"),
                )
            ),
            agent_id=normalize_identifier(attribute_or_mapping(context, "agent_id", "id")),
            tool_name=normalize_identifier(tool),
            operation=operation,
            framework=self.framework,
            function_name=getattr(func, "__name__", None),
            inputs=args,
            kwargs=dict(kwargs),
            run_id=normalize_identifier(attribute_or_mapping(context, "run_id", "thread_id")),
            trace_id=normalize_identifier(attribute_or_mapping(context, "trace_id")),
            parent_span_id=normalize_identifier(attribute_or_mapping(context, "parent_span_id")),
            attributes=attrs,
        )
