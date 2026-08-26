"""Low-cardinality OpenTelemetry metrics for instrumented operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from opentelemetry.metrics import Counter, Histogram, Meter, UpDownCounter

MetricAttributes = Mapping[str, str]


@dataclass(frozen=True, slots=True)
class OperationMetrics:
    """Metric instruments emitted by the interceptor."""

    invocations: Counter
    duration: Histogram
    errors: Counter
    cancellations: Counter
    active: UpDownCounter
    input_tokens: Counter
    output_tokens: Counter

    @classmethod
    def create(cls, meter: Meter) -> OperationMetrics:
        """Create all instruments from a meter."""
        return cls(
            invocations=meter.create_counter(
                "aae.observability.operation.invocations",
                unit="{invocation}",
                description="Number of instrumented operations started.",
            ),
            duration=meter.create_histogram(
                "aae.observability.operation.duration",
                unit="s",
                description="Instrumented operation duration in seconds.",
            ),
            errors=meter.create_counter(
                "aae.observability.operation.errors",
                unit="{error}",
                description="Number of instrumented operations that failed.",
            ),
            cancellations=meter.create_counter(
                "aae.observability.operation.cancellations",
                unit="{cancellation}",
                description="Number of cancelled instrumented operations.",
            ),
            active=meter.create_up_down_counter(
                "aae.observability.operation.active",
                unit="{operation}",
                description="Number of currently active instrumented operations.",
            ),
            input_tokens=meter.create_counter(
                "gen_ai.client.token.usage.input",
                unit="{token}",
                description="Input tokens reported by a framework adapter.",
            ),
            output_tokens=meter.create_counter(
                "gen_ai.client.token.usage.output",
                unit="{token}",
                description="Output tokens reported by a framework adapter.",
            ),
        )
