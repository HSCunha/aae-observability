"""Typed telemetry records."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from time import time_ns
from typing import Any


class SignalType(str, Enum):
    SPAN = "span"
    METRIC = "metric"
    LOG = "log"


@dataclass(frozen=True, slots=True)
class TelemetryEnvelope:
    signal_type: SignalType
    payload: Any
    timestamp_ns: int = field(default_factory=time_ns)
    trace_id: str | None = None
    attributes: Mapping[str, str | bool | int | float] = field(default_factory=dict)
