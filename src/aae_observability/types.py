"""Public governance types."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    """Possible governance decisions."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    REDACT = "redact"
    KILL = "kill"


@dataclass(frozen=True, slots=True)
class PolicyResult:
    """Result returned by a governance policy evaluation."""

    verdict: Verdict = Verdict.ALLOW
    reason: str = ""
    rule_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        """Whether execution is allowed to continue."""
        return self.verdict is Verdict.ALLOW
