"""Safe condition compiler; no eval, imports, or executable expressions."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from aae_observability.contracts import ActionSnapshot

Predicate = Callable[[ActionSnapshot], bool]
_ALLOWED_ROOTS = {"call", "identity", "context"}


def _read(snapshot: ActionSnapshot, path: str) -> Any:
    parts = path.split(".")
    if not parts or parts[0] not in _ALLOWED_ROOTS:
        raise ValueError(f"condition path must start with one of {sorted(_ALLOWED_ROOTS)}")
    value: Any = getattr(snapshot, parts[0])
    for part in parts[1:]:
        value = value.get(part) if isinstance(value, Mapping) else getattr(value, part, None)
    return value


def compile_condition(spec: Mapping[str, Any]) -> Predicate:
    """Compile a declarative condition tree into a snapshot predicate."""
    if not spec:
        return lambda snapshot: True
    if "all" in spec:
        children = tuple(compile_condition(x) for x in spec["all"])
        return lambda snapshot: all(fn(snapshot) for fn in children)
    if "any" in spec:
        children = tuple(compile_condition(x) for x in spec["any"])
        return lambda snapshot: any(fn(snapshot) for fn in children)
    if "not" in spec:
        child = compile_condition(spec["not"])
        return lambda snapshot: not child(snapshot)
    path = spec.get("field")
    if not isinstance(path, str):
        raise ValueError("leaf condition requires string field")
    root = path.split(".", 1)[0]
    if root not in _ALLOWED_ROOTS:
        raise ValueError(f"condition path must start with one of {sorted(_ALLOWED_ROOTS)}")
    operators = [
        name
        for name in (
            "eq",
            "ne",
            "in",
            "not_in",
            "contains",
            "matches",
            "exists",
            "gt",
            "ge",
            "lt",
            "le",
        )
        if name in spec
    ]
    if len(operators) != 1:
        raise ValueError("leaf condition requires exactly one supported operator")
    operator = operators[0]
    expected = spec[operator]
    if operator == "matches":
        if not isinstance(expected, str) or len(expected) > 512:
            raise ValueError("matches requires a pattern of at most 512 characters")
        pattern = re.compile(expected)
        return lambda snapshot: bool(pattern.fullmatch(str(_read(snapshot, path) or "")))

    def predicate(snapshot: ActionSnapshot) -> bool:
        actual = _read(snapshot, path)
        if operator == "eq":
            return actual == expected
        if operator == "ne":
            return actual != expected
        if operator == "in":
            return actual in expected
        if operator == "not_in":
            return actual not in expected
        if operator == "contains":
            return actual is not None and expected in actual
        if operator == "exists":
            return (actual is not None) is bool(expected)
        if operator == "gt":
            return actual is not None and actual > expected
        if operator == "ge":
            return actual is not None and actual >= expected
        if operator == "lt":
            return actual is not None and actual < expected
        if operator == "le":
            return actual is not None and actual <= expected
        return False

    return predicate
