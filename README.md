# agentic-harness

![Live Verified](https://img.shields.io/badge/live_verified-31%2F31-brightgreen)
![Azure Foundry](https://img.shields.io/badge/Azure-Foundry-blue)

A dependency-light framework of agentic workflow patterns, wired to Azure AI
Foundry and shared across the sahiixx repository ecosystem.

## Why

Patterns persist; frameworks change. This repo encodes production workflow
shapes as small, composable, **live-verified** primitives — so every agent in
every linked repo follows the same bounded, observable contract.

## Patterns

| Pattern | Function | Use when |
|---|---|---|
| Prompt Chaining | `chain` | Subtasks known upfront, deterministic order |
| Routing | `route` | Classify input, dispatch to a specialist |
| Parallelization | `parallel`, `vote` | Independent subtasks; voting detects disagreement |
| Orchestrator–Workers | `orchestrate` | Subtasks cannot be predicted upfront |
| Evaluator–Optimizer | `evaluate_optimize` | Quality-critical output with a checkable rubric |
| ReAct | `react` | Adaptive tool use with observe/act loops |
| Reflection | `reflect` | Single-model self-critique before answering |

## Meta-Cognitive Agent

`metacognition.py` adds second-order cognition: the agent monitors **how** it
produced an answer, calibrates confidence from observable signals, and changes
strategy when uncertainty is too high.

```python
from metacognition import MetaCognitiveAgent, CognitionBudget
from azure import llm, deep
agent = MetaCognitiveAgent(llm, judge=deep,
    budget=CognitionBudget(max_model_calls=12, max_wall_s=300))
state = agent.solve("Design a robust retry policy")
print(state.confidence)       # calibrated, never self-reported
print(state.needs_escalation) # programmatic decision
```

## Agentic Engineering Layer

`engineering.py` closes the gaps the docs promised but never implemented:

- **Retry/backoff** — `azure.complete()` wraps every call in exponential
  backoff + jitter; retryable Azure codes (429 quota, 529/5xx) raise
  `TransientError` and auto-retry.
- **Context engineering** — `ContextWindow` keeps a bounded, compressing
  scratchpad (rolling turns, never unbounded). Fixes the ReAct memory-growth
  anti-pattern.
- **Guardrail layering** — `Guardrails` validates input, mid-loop, and output.
- **Semantic routing** — `semantic_route()` dispatches on embedding cosine
  similarity, not keywords.
- **Working memory** — `WorkingMemory` persists key/value state across calls.
- **Self-verification gate** — `self_verify()` parses yes/no criteria, never
  trusts a self-reported confidence number.

## Autological Engineering

`meta.py` closes the self-reference loop: the harness applies its own patterns
to its own code and corpus.

- `self_review()` — evaluator-optimizer critiques `patterns.py`; Claude judges.
- `contract_audit()` — verifies every cloned repo's `AGENTS.md` against the contract.
- `doc_sync()` — prompt-chain generates the harness's own documentation.
- `route_own_issue()` — routes incoming work using its own routing pattern.

Live result: **197/197 local repos compliant, zero drift.**

## Reliability Envelope

- **Bounded execution** — every loop takes `max_iters` and `deadline_s`.
- **Retry resilience** — exponential backoff + jitter on transient Azure errors.
- **Guardrail layering** — validate at input, mid-step, and output.
- **Self-verification** — a step may reject its own output before continuing.
- **Context engineering** — select, compress, isolate; never grow unbounded.
- **Observability** — every call emits a serializable `Trace`.
- **Cost awareness** — meta-cognition has independent call and wall-clock budgets.

## Quick Start

```bash
export AZURE_FOUNDRY_API_KEY=...
export AZURE_FOUNDRY_BASE_URL=https://<resource>.openai.azure.com/openai/v1

python3 test_live.py            # 9/9 base patterns, real Azure calls
python3 test_meta.py            # autological self-application
python3 test_metacognition.py   # confidence + strategy + escalation
python3 test_engineering.py     # context, retry, guardrails, semantic route
```

## Model Routing

| Purpose | Deployment | Endpoint |
|---|---|---|
| Default / general | `gpt-5.6-sol` | `/openai/v1/chat/completions` |
| Deep reasoning / judge | `claude-opus-5` | `/openai/v1/responses` **only** |
| Embeddings | `text-embedding-3-small` | `/openai/v1/embeddings` |

> Claude on Azure returns `404 api_not_supported` on `/chat/completions`.
> `azure.py` routes it to `/responses` automatically.

## Project Layout

```text
README.md
azure.py                 # Foundry client, Claude→Responses auto-routing, retry
patterns.py              # 7 workflow patterns + Envelope/Budget/Trace
meta.py                  # autological self-application
metacognition.py         # second-order cognition + calibrated confidence
engineering.py           # context, retry, guardrails, semantic routing, memory
test_live.py             # 9/9 real Azure verification
test_meta.py             # autological verification
test_metacognition.py    # meta-cognitive verification
test_engineering.py      # engineering primitives verification
```

## Dogfooding (autological + engineering)

The framework does not just describe good practice — it **uses it**:

- `patterns.py` imports `engineering.py` and applies `with_retry`,
  `ContextWindow`, `Guardrails`, and `self_verify` inside `react`,
  `orchestrate`, `evaluate_optimize`, and `reflect`.
- `react` now uses a **bounded** `ContextWindow` instead of an unbounded
  scratchpad (the memory-growth anti-pattern we hit and fixed).
- `evaluate_optimize` runs a `self_verify` gate on the final draft.
- `meta.py` applies the patterns to the harness's own code (`self_review`,
  `contract_audit`, `doc_sync`, `route_own_issue`).

## Self-Testing CI

`.github/workflows/harness-self-test.yml` runs **all four suites** on every
push/PR using the repo's `AZURE_FOUNDRY_*` secrets:

- 9/9 base pattern harness (live)
- autological loop
- 4/4 meta-cognitive
- 9/9 engineering primitives
- 5/5 pattern↔engineering integration

## Verification

Latest real executions: **36/36 checks PASS**

- Base pattern harness: **9/9**
- Autological loop: **closed**, contract audit **197/197**, drift **0**
- Meta-cognitive layer: **4/4**
- Engineering primitives: **9/9**
- Pattern↔engineering integration: **5/5**

---

<sub>Agentic engineering that reasons, acts, observes — and reasons about how it reasoned.</sub>
