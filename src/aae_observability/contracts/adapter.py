"""Framework adapter contract and generic fallback adapter."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from aae_observability.contracts.snapshot import AgentCall, Framework


@runtime_checkable
class FrameworkAdapter(Protocol):
    """Normalize framework-specific calls into ``AgentCall`` snapshots."""

    framework: Framework

    def matches(self, func: Callable[..., Any]) -> bool:
        """Return whether this adapter handles the callable."""
        ...

    def extract_context(
        self,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: Mapping[str, Any],
    ) -> AgentCall:
        """Normalize a function invocation."""
        ...


class BaseFrameworkAdapter(ABC):
    """Inheritance-based convenience contract for framework adapters."""

    framework = Framework.GENERIC

    def matches(self, func: Callable[..., Any]) -> bool:
        del func
        return False

    @abstractmethod
    def extract_context(
        self,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: Mapping[str, Any],
    ) -> AgentCall:
        """Normalize a function invocation."""
        raise NotImplementedError


class GenericFrameworkAdapter(BaseFrameworkAdapter):
    """Fallback adapter for any Python callable."""

    framework = Framework.GENERIC

    def matches(self, func: Callable[..., Any]) -> bool:
        return callable(func)

    def extract_context(
        self,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: Mapping[str, Any],
    ) -> AgentCall:
        return AgentCall(
            agent_name=getattr(func, "__aae_observability_agent_name__", None),
            tool_name=getattr(func, "__aae_observability_tool_name__", None),
            operation=getattr(func, "__aae_observability_operation__", None),
            framework=self.framework,
            function_name=getattr(func, "__name__", None),
            inputs=args,
            kwargs=dict(kwargs),
        )
