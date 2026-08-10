# agentic-harness

![Live Verified](https://img.shields.io/badge/live_verified-9%2F9-brightgreen)
![Meta Cognition](https://img.shields.io/badge/meta--cognition-active-purple)
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

agent = MetaCognitiveAgent(
    llm, judge=deep,
    budget=CognitionBudget(max_model_calls=12, max_wall_s=300))
state = agent.solve(
    "Design a robust retry policy",
    rubric="Bounded, idempotent, jittered, circuit-broken, dead-lettered")

print(state.answer)
print(state.confidence)       # calibrated, never self-reported
print(state.needs_escalation) # programmatic decision
print(state.report())         # JSON-serializable audit artifact
```

### Meta-cognitive loop

```text
task → select least-complex strategy → execute → inspect trace
     → extract explicit evidence/assumptions/uncertainty
     → calibrate from agreement + verifier + tools + evidence
     → escalate once if needed → answer + epistemic report
```

Confidence does **not** come from asking the model “how confident are you?” It is
computed from independent signals: vote agreement, judge outcome, evidence count,
tool errors, contradictions, and budget consumption.

## Autological Engineering

`meta.py` closes the self-reference loop: the harness applies its own patterns
to its own code and corpus.

- `self_review()` — evaluator-optimizer critiques `patterns.py`; Claude judges.
- `contract_audit()` — verifies every cloned repo's `AGENTS.md` against the contract.
- `doc_sync()` — prompt-chain generates the harness's own documentation.
- `route_own_issue()` — routes incoming work using its own routing pattern.
- `think_about_self()` — reflection applied to the harness's own design.

Live result: **197/197 local repos compliant, zero drift.**

## Reliability Envelope

- **Bounded execution** — every loop takes `max_iters` and `deadline_s`.
- **Guardrail layering** — validate at input, mid-step, and output.
- **Self-verification** — a step may reject its own output before continuing.
- **Context engineering** — select, compress, isolate; never grow unbounded.
- **Observability** — every call emits a serializable `Trace`.
- **Cost awareness** — meta-cognition has independent call and wall-clock budgets.
- **Epistemic reporting** — explicit evidence, assumptions, uncertainty, contradictions.

## Quick Start

```bash
export AZURE_FOUNDRY_API_KEY=...
export AZURE_FOUNDRY_BASE_URL=https://<resource>.openai.azure.com/openai/v1

python3 test_live.py            # 9/9 base patterns, real Azure calls
python3 test_meta.py            # autological self-application
python3 test_metacognition.py   # confidence + strategy + escalation
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
azure.py                 # Foundry client, Claude→Responses auto-routing
patterns.py              # 7 workflow patterns + Envelope/Budget/Trace
meta.py                  # autological self-application
metacognition.py         # second-order cognition + calibrated confidence
test_live.py             # 9/9 real Azure verification
test_meta.py             # autological verification
test_metacognition.py    # meta-cognitive verification
```

## Verification

Latest real executions:

- Base pattern harness: **9/9 PASS**
- Autological loop: **closed**, contract audit **197/197**, drift **0**
- Meta-cognitive layer: **4/4 PASS**
  - selected `evaluate_optimize`
  - Claude judge passed output
  - calibrated confidence `0.717`
  - model calls `7/12`
  - contradictions `0`

---

<sub>Agentic engineering that reasons, acts, observes — and reasons about how it reasoned.</sub>
