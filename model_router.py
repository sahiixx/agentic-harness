"""
Provider-neutral model router for agentic-harness.

Resolves task_class → binding. Application code should call select_binding()
instead of hardcoding Azure deployment names (gpt-5.6-sol, claude-opus-5).

Maps capability slots onto azure.DEFAULT / azure.DEEP when those are the
configured hosted providers.
"""

from __future__ import annotations

from typing import Any, Optional

ROUTING_TABLE: dict[str, dict[str, Any]] = {
    "classify": {
        "preferred": "local_fast",
        "fallback": ["hosted_general"],
        "constraints": {"max_latency_ms": 800, "structured_output": True},
    },
    "extract": {
        "preferred": "local_structured",
        "fallback": ["hosted_general"],
        "constraints": {"max_latency_ms": 1500, "structured_output": True},
    },
    "plan": {
        "preferred": "hosted_reasoning",
        "fallback": ["local_reasoning", "hosted_general"],
        "constraints": {"max_latency_ms": 8000, "structured_output": False},
    },
    "voice": {
        "preferred": "realtime_low_latency",
        "fallback": [],
        "constraints": {"max_latency_ms": 400, "structured_output": False},
    },
    "judge": {
        "preferred": "independent_evaluator",
        "fallback": ["hosted_reasoning"],
        "constraints": {"max_latency_ms": 5000, "structured_output": True, "must_differ_from": "plan"},
    },
    "enrich": {
        "preferred": "hosted_general",
        "fallback": [],
        "constraints": {"max_latency_ms": 10000},
    },
}

CAPABILITY_SLOTS: dict[str, dict[str, str]] = {
    "local_fast": {"provider": "ollama", "model": "qwen2.5-3b"},
    "local_structured": {"provider": "ollama", "model": "qwen2.5-7b"},
    "local_reasoning": {"provider": "ollama", "model": "qwen2.5-32b"},
    "hosted_general": {"provider": "azure", "model": "gpt-5.6-sol"},
    "hosted_reasoning": {"provider": "azure", "model": "claude-opus-5"},
    "realtime_low_latency": {"provider": "openai", "model": "gpt-4o-realtime-preview"},
    "independent_evaluator": {"provider": "azure", "model": "claude-opus-5"},
}

_HEALTH: dict[str, bool] = {s: True for s in CAPABILITY_SLOTS}


def set_slot_health(slot: str, healthy: bool) -> None:
    if slot in _HEALTH:
        _HEALTH[slot] = healthy


def select_binding(
    task_class: str,
    *,
    privacy_tier: str = "tenant_ok",
    structured_output: Optional[bool] = None,
    exclude_slots: Optional[set[str]] = None,
) -> dict[str, Any]:
    if task_class not in ROUTING_TABLE:
        raise ValueError(f"Unknown task_class: {task_class}")

    entry = ROUTING_TABLE[task_class]
    constraints = entry["constraints"]
    candidates = [entry["preferred"]] + list(entry.get("fallback") or [])
    exclude = exclude_slots or set()
    need_structured = constraints.get("structured_output", False)
    if structured_output is not None:
        need_structured = structured_output

    for slot in candidates:
        if slot in exclude or not _HEALTH.get(slot, True):
            continue
        binding = CAPABILITY_SLOTS.get(slot)
        if not binding:
            continue
        if privacy_tier == "local_only" and not slot.startswith("local_"):
            continue
        if need_structured and slot in {"hosted_reasoning", "local_reasoning"} and task_class != "plan":
            continue
        return {
            "task_class": task_class,
            "binding": slot,
            "provider": binding["provider"],
            "model": binding["model"],
            "constraints": constraints,
        }

    raise RuntimeError(f"No valid route for task_class={task_class}")


def model_for(task_class: str, **kwargs: Any) -> str:
    """Return the deployment/model id for azure.complete(..., model=...)."""
    return select_binding(task_class, **kwargs)["model"]


def complete_for(task_class: str, prompt: str, **kwargs: Any) -> str:
    """Route + complete via azure client when provider is azure."""
    import azure

    sel = select_binding(task_class, **kwargs)
    if sel["provider"] == "azure":
        return azure.complete(prompt, model=sel["model"])
    raise RuntimeError(
        f"Provider {sel['provider']} not wired in this process; "
        f"use model={sel['model']} with your local client"
    )


__all__ = [
    "ROUTING_TABLE",
    "CAPABILITY_SLOTS",
    "select_binding",
    "model_for",
    "complete_for",
    "set_slot_health",
]
