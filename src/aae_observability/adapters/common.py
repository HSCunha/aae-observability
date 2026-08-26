from collections.abc import Callable, Mapping
from typing import Any


def first_value(*values: Any) -> Any | None:
    return next((v for v in values if v is not None and v != ""), None)


def attribute_or_mapping(value: Any, *names: str) -> Any | None:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        candidate = getattr(value, name, None)
        if candidate is not None:
            return candidate
    return None


def module_name(func: Callable[..., Any]) -> str:
    return str(getattr(func, "__module__", "")).lower()


def class_name(func: Callable[..., Any]) -> str:
    owner = getattr(func, "__self__", None)
    return (owner if owner is not None else func).__class__.__name__.lower()


def normalize_identifier(value: Any) -> str | None:
    return None if value is None else str(value)


def token_attributes(*sources: Any) -> dict[str, int]:
    aliases = {
        "gen_ai.usage.input_tokens": (
            "input_tokens",
            "prompt_tokens",
            "input_token_count",
            "prompt_token_count",
        ),
        "gen_ai.usage.output_tokens": (
            "output_tokens",
            "completion_tokens",
            "output_token_count",
            "completion_token_count",
        ),
    }
    result: dict[str, int] = {}
    for normalized, names in aliases.items():
        for source in sources:
            value = attribute_or_mapping(source, *names)
            if isinstance(value, int) and value >= 0:
                result[normalized] = value
                break
    return result
