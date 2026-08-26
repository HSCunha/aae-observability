from dataclasses import dataclass

from opentelemetry.metrics import Counter, Histogram, Meter


@dataclass(slots=True)
class GovernanceMetrics:
    decisions: Counter
    duration: Histogram
    errors: Counter
    timeouts: Counter

    @classmethod
    def create(cls, meter: Meter):
        return cls(
            meter.create_counter("aae.observability.governance.decisions", unit="{decision}"),
            meter.create_histogram("aae.observability.governance.duration", unit="s"),
            meter.create_counter("aae.observability.governance.errors", unit="{error}"),
            meter.create_counter("aae.observability.governance.timeouts", unit="{timeout}"),
        )
