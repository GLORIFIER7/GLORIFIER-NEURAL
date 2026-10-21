from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


AuditEventType = Literal[
    "task_received",
    "policy_denied",
    "approval_required",
    "inference_started",
    "inference_completed",
    "inference_failed",
]
AuditStatus = Literal[
    "FULLY VERIFIED",
    "VERIFIED",
    "PARTIALLY VERIFIED",
    "NOT VERIFIED",
    "DEGRADED",
    "NOT OBSERVABLE",
]


@dataclass(frozen=True)
class AuditEvent:
    """Minimal audit record; deliberately excludes prompts, tokens, and raw provider errors."""

    request_id: str
    event_type: AuditEventType
    status: AuditStatus
    action_class: str
    provider: str | None = None
    evidence: tuple[str, ...] = ()


class AuditSink:
    """Persistence boundary. Implementations must be explicitly injected; no implicit writes."""

    def write(self, event: AuditEvent) -> None:
        """Persist one sanitized event or raise an exception if persistence fails."""
        raise NotImplementedError
