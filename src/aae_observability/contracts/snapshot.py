"""Framework-neutral snapshots exchanged between aae_observability components."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from time import time_ns
from typing import Any


class Framework(str, Enum):
    """Supported framework families for normalized calls."""

    MICROSOFT_AGENT_FRAMEWORK = "microsoft_agent_framework"
    LANGCHAIN = "langchain"
    MULTI_AGENT = "multi_agent"
    GENERIC = "generic"


class OperationType(str, Enum):
    """Normalized GenAI operation types used for spans and metrics."""

    AGENT_RUN = "agent.run"
    LLM_CHAT = "llm.chat"
    TOOL_CALL = "tool.call"
    RETRIEVAL_QUERY = "retrieval.query"
    AGENT_HANDOFF = "agent.handoff"


@dataclass(frozen=True, slots=True)
class Identity:
    """Identity associated with an agent action."""

    principal_id: str | None = None
    principal_type: str | None = None
    tenant_id: str | None = None
    roles: tuple[str, ...] = ()
    claims: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentCall:
    """Framework-neutral representation of an agent or tool invocation."""

    agent_name: str | None = None
    agent_id: str | None = None
    tool_name: str | None = None
    operation: OperationType | str | None = None
    framework: Framework = Framework.GENERIC
    function_name: str | None = None
    inputs: tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    start_time_ns: int = field(default_factory=time_ns)
    attributes: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_tool_call(self) -> bool:
        """Return whether this snapshot represents a named tool call."""
        return self.tool_name is not None


@dataclass(frozen=True, slots=True)
class ActionSnapshot:
    """Complete immutable input to a governance policy decision."""

    call: AgentCall
    identity: Identity = field(default_factory=Identity)
    context: Mapping[str, Any] = field(default_factory=dict)
