from collections.abc import Iterable
from importlib.metadata import EntryPoint, entry_points
from typing import Any

from aae_observability.adapters.langchain import LangChainAdapter
from aae_observability.adapters.maf import MicrosoftAgentFrameworkAdapter
from aae_observability.adapters.multiagent import MultiAgentAdapter
from aae_observability.contracts import FrameworkAdapter, GenericFrameworkAdapter

ENTRY_POINT_GROUP = "aae.observability.framework_adapters"


def default_adapters() -> tuple[FrameworkAdapter, ...]:
    return (
        MultiAgentAdapter(),
        MicrosoftAgentFrameworkAdapter(),
        LangChainAdapter(),
        GenericFrameworkAdapter(),
    )


def _selected_entry_points() -> Iterable[EntryPoint]:
    found = entry_points()
    return (
        found.select(group=ENTRY_POINT_GROUP)
        if hasattr(found, "select")
        else found.get(ENTRY_POINT_GROUP, ())
    )


def discover_adapters(*, strict: bool = False) -> tuple[FrameworkAdapter, ...]:
    loaded = []
    for ep in _selected_entry_points():
        try:
            value: Any = ep.load()
            adapter = value() if isinstance(value, type) else value
            if not isinstance(adapter, FrameworkAdapter):
                raise TypeError(f"entry point {ep.name!r} does not implement FrameworkAdapter")
            loaded.append(adapter)
        except Exception:
            if strict:
                raise
    return tuple(loaded)


def build_adapter_registry(
    explicit: tuple[FrameworkAdapter, ...] | None = None, *, discover_plugins: bool = True
) -> tuple[FrameworkAdapter, ...]:
    values = (
        list(explicit)
        if explicit is not None
        else ([*discover_adapters()] if discover_plugins else []) + list(default_adapters())
    )
    if not any(isinstance(a, GenericFrameworkAdapter) for a in values):
        values.append(GenericFrameworkAdapter())
    return tuple(values)
