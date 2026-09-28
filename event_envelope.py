"""
Canonical event envelope for agentic-harness.

Aligns with sahiixx-production-hardening/contracts/event-envelope.json.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

EVENT_TYPES = frozenset({
    "lead.received", "lead.normalized", "lead.consent_verified", "lead.qualified",
    "lead.matched", "lead.contacted", "lead.replied",
    "appointment.booked", "appointment.showed", "appointment.no_show",
    "deal.created", "deal.won", "deal.lost",
    "commission.recorded", "revenue.attributed",
    "agent.run.started", "agent.run.completed", "agent.run.failed",
    "human.approval.requested", "human.approval.granted", "human.approval.denied",
    "memory.written", "memory.superseded",
    "system.health", "system.remediation",
})

CHANNELS = frozenset({
    "telegram", "web_form", "crm", "api", "voice", "whatsapp", "email", "internal",
})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_event(
    event_type: str,
    payload: dict[str, Any],
    *,
    tenant_id: str,
    source_channel: str,
    source_system: str,
    actor_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    agent_run_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    model: Optional[str] = None,
    cost_usd: float = 0.0,
    human_approved: bool = False,
    tokens_in: int = 0,
    tokens_out: int = 0,
    entities: Optional[dict[str, str]] = None,
    event_version: str = "1.0",
) -> dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unsupported event_type: {event_type}")
    if source_channel not in CHANNELS:
        raise ValueError(f"Unsupported source_channel: {source_channel}")
    if not tenant_id:
        raise ValueError("tenant_id is required")

    event_id = str(uuid.uuid4())
    event: dict[str, Any] = {
        "event_id": event_id,
        "event_type": event_type,
        "event_version": event_version,
        "occurred_at": utc_now(),
        "ingested_at": utc_now(),
        "tenant_id": tenant_id,
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "causation_id": causation_id,
        "idempotency_key": idempotency_key or f"{event_type}:{event_id}",
        "source": {
            "channel": source_channel,
            "system": source_system,
            "actor_id": actor_id,
        },
        "payload": payload,
    }
    if any([agent_run_id, agent_id, workflow_id, model, cost_usd, human_approved, tokens_in, tokens_out]):
        event["agent"] = {
            "agent_run_id": agent_run_id,
            "agent_id": agent_id,
            "workflow_id": workflow_id,
            "model": model,
            "cost_usd": float(cost_usd),
            "human_approved": bool(human_approved),
            "tokens_in": int(tokens_in),
            "tokens_out": int(tokens_out),
        }
    if entities:
        event["entities"] = {k: v for k, v in entities.items() if v}
    return event


__all__ = ["build_event", "EVENT_TYPES", "CHANNELS", "utc_now"]
