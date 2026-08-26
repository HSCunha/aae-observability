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


class LangChainAdapter(BaseFrameworkAdapter):
    framework = Framework.LANGCHAIN

    def matches(self, func: Callable[..., Any]) -> bool:
        module, name = module_name(func), class_name(func)
        return bool(
            getattr(func, "__aae_observability_langchain__", False)
            or module.startswith("langchain")
            or module.startswith("langgraph")
            or any(x in name for x in ("runnable", "chain", "retriever", "basetool"))
        )

    def extract_context(
        self, func: Callable[..., Any], args: tuple[Any, ...], kwargs: Mapping[str, Any]
    ) -> AgentCall:
        config = kwargs.get("config")
        callbacks = attribute_or_mapping(config, "callbacks")
        metadata = attribute_or_mapping(config, "metadata") or kwargs.get("metadata")
        run_type = str(
            first_value(
                attribute_or_mapping(metadata, "run_type", "type"),
                getattr(func, "__aae_observability_langchain_type__", None),
                class_name(func),
            )
        ).lower()
        tool = first_value(
            getattr(func, "__aae_observability_tool_name__", None),
            attribute_or_mapping(metadata, "tool_name"),
        )
        operation = getattr(func, "__aae_observability_operation__", None) or (
            OperationType.RETRIEVAL_QUERY
            if "retriev" in run_type
            else OperationType.TOOL_CALL
            if tool or "tool" in run_type
            else OperationType.LLM_CHAT
            if any(x in run_type for x in ("llm", "chat", "model"))
            else OperationType.AGENT_RUN
        )
        return AgentCall(
            agent_name=normalize_identifier(
                first_value(
                    getattr(func, "__aae_observability_agent_name__", None),
                    attribute_or_mapping(metadata, "agent_name", "name"),
                )
            ),
            tool_name=normalize_identifier(tool),
            operation=operation,
            framework=self.framework,
            function_name=getattr(func, "__name__", None),
            inputs=args,
            kwargs=dict(kwargs),
            run_id=normalize_identifier(
                first_value(
                    kwargs.get("run_id"),
                    attribute_or_mapping(config, "run_id"),
                    attribute_or_mapping(callbacks, "run_id"),
                )
            ),
            parent_span_id=normalize_identifier(
                first_value(
                    kwargs.get("parent_run_id"), attribute_or_mapping(config, "parent_run_id")
                )
            ),
            attributes=token_attributes(
                kwargs.get("usage_metadata"), kwargs.get("response_metadata"), metadata
            ),
        )
