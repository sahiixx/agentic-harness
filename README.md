# agentic-harness

A dependency-light framework of agentic workflow patterns, wired to your Azure
AI Foundry deployments and shared across all `sahiixx` repositories.

## Why

Patterns persist; frameworks change. This repo encodes the workflow shapes that
recur across your 84 authored repositories as small, composable, **verified**
primitives — so any agent working in any repo can reach for the same contract.

## Patterns (all verified live against Azure)

| Pattern | Function | Use when |
|---|---|---|
| Prompt Chaining | `chain` | Subtasks known upfront, deterministic order |
| Routing | `route` | Classify input, dispatch to a specialist |
| Parallelization | `parallel`, `vote` | Independent subtasks; voting detects disagreement |
| Orchestrator–Workers | `orchestrate` | Subtasks **cannot** be predicted upfront |
| Evaluator–Optimizer | `evaluate_optimize` | Quality-critical output with a checkable rubric |
| ReAct | `react` | Adaptive tool use with observe/act loops |
| Reflection | `reflect` | Single-model self-critique before answering |

## Reliability envelope (enforced everywhere)

- **Bounded execution** — every loop takes `max_iters` and a `deadline_s`.
- **Guardrail layering** — validate at input, mid-step, and output.
- **Self-verification** — a step may reject its own output before continuing.
- **Context engineering** — select, compress, isolate; never grow unbounded.
- **Observability** — every call emits a `Trace` you can serialize with `trace.json()`.

## Quick start

```bash
export AZURE_FOUNDRY_API_KEY=...
export AZURE_FOUNDRY_BASE_URL=https://<resource>.openai.azure.com/openai/v1
python3 test_live.py        # 9/9 patterns, real Azure calls
```

```python
from harness import llm, deep
from patterns import orchestrate, Envelope

out = orchestrate(
    llm,
    'Summarize the agentic-harness README in 3 bullets.',
    lambda s: llm(s),
    Envelope(max_iters=3))
```

## Model routing

| Purpose | Deployment | Endpoint |
|---|---|---|
| Default / general | `gpt-5.6-sol` | `/openai/v1/chat/completions` |
| Deep reasoning (judge) | `claude-opus-5` | `/openai/v1/responses` **only** |
| Embeddings | `text-embedding-3-small` | `/openai/v1/embeddings` |

> Claude on Azure returns `404 api_not_supported` on `/chat/completions`.
> The `azure.py` client routes it to `/responses` automatically — you never
> think about it.

## Project layout

```
harness/
  patterns.py      # 7 workflow patterns + Envelope/Budget/Trace
  azure.py         # Foundry client with Claude->Responses routing
  test_live.py     # real end-to-end verification (9/9 PASS)
```

## Related

- 84 authored repositories share this contract; each carries `AGENTS.md`
  + `README.md` describing its role in the harness.
- The pattern taxonomy follows Anthropic's *Building Effective Agents* plus the
  2025–2026 emergent patterns (Context Engineering, Tool Sandboxing).

---

<sub>Maintained by the agentic harness · generated from live verification.</sub>
