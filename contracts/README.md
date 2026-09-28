# Production contracts

Authoritative schemas live in **[sahiixx-production-hardening](https://github.com/sahiixx/sahiixx-production-hardening)**:

| Contract | Path in hardening pack |
|----------|------------------------|
| Event envelope | `contracts/event-envelope.json` |
| Model routing | `contracts/model-routing.yaml` |
| Python stubs | `stubs/python/event_envelope.py`, `model_router.py` |

## Rules

1. **Do not hardcode** Azure deployment names (`gpt-5.6-sol`, `claude-opus-5`) in application code.
2. Resolve models via the provider-neutral router (`task_class` → binding).
3. Every agent run must emit events using the canonical envelope (idempotency_key, correlation_id, cost, model).
4. Port `stubs/python/` into this repo or a shared package and keep them in sync with the hardening pack.

See also: [PRODUCTION_ARCHITECTURE.md](https://github.com/sahiixx/sahiixx-production-hardening/blob/main/docs/PRODUCTION_ARCHITECTURE.md)
