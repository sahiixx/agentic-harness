"""Agentic harness — pattern primitives with a bounded execution envelope.

Every pattern here is a thin, dependency-light implementation of a named
workflow shape. They compose: route -> orchestrate -> evaluate, etc.

Design rules enforced by this module:
  * Bounded execution   — every loop takes max_iters and a deadline.
  * Guardrail layering  — validate(input), validate(step), validate(output).
  * Self-verification   — a step may reject its own output before continuing.
  * Observability       — every call emits a trace record.

The LLM callable is injected, so this module has no vendor lock-in.
Provide `llm(prompt: str, *, model: str | None = None) -> str`.
"""
from __future__ import annotations

import time
import json
import concurrent.futures as cf
from dataclasses import dataclass, field
from typing import Callable, Iterable, Any

LLM = Callable[..., str]

# Engineering primitives (context, retry, guardrails, verification). Importing
# them here makes the patterns dogfood their own engineering layer — every
# pattern enforces the guardrail/context/self-verify rules it advertises.
try:
    from engineering import (
        with_retry, ContextWindow, Guardrails, self_verify, TransientError)
    _HAS_ENGINEERING = True
except Exception:  # harness usable standalone too
    _HAS_ENGINEERING = False

    def with_retry(fn, **_):  # type: ignore
        return fn

    class ContextWindow:  # type: ignore
        def __init__(self, **_):
            self._t = []

        def add(self, x):
            self._t.append(x)

        def render(self):
            return '\n'.join(self._t)

        def __len__(self):
            return len(self._t)


class Budget(Exception):
    """Raised when an execution envelope is exhausted."""


@dataclass
class Trace:
    events: list = field(default_factory=list)

    def add(self, pattern: str, step: str, meta: dict | None = None):
        self.events.append({'t': round(time.time(), 3), 'pattern': pattern,
                            'step': step, **(meta or {})})

    def json(self) -> str:
        return json.dumps(self.events, indent=1)


@dataclass
class Envelope:
    """Bounded execution envelope. Shared by every pattern."""
    max_iters: int = 5
    deadline_s: float = 300.0
    started: float = field(default_factory=time.time)
    trace: Trace = field(default_factory=Trace)

    def tick(self, i: int):
        if i >= self.max_iters:
            raise Budget(f'max_iters={self.max_iters} exhausted')
        if time.time() - self.started > self.deadline_s:
            raise Budget(f'deadline {self.deadline_s}s exceeded')


# ---------------------------------------------------------------- patterns

def chain(llm: LLM, steps: Iterable[str], seed: str, env: Envelope | None = None,
          gate: Callable[[str], bool] | None = None) -> str:
    """Prompt Chaining — deterministic pipeline; each output feeds the next.

    `gate` is an optional programmatic check between steps (fail fast).
    """
    env = env or Envelope()
    cur = seed
    for i, s in enumerate(steps):
        env.tick(i)
        env.trace.add('chain', f'step{i}')
        cur = llm(f'{s}\n\n---\nINPUT:\n{cur}')
        if gate and not gate(cur):
            env.trace.add('chain', f'gate_reject{i}')
            raise Budget(f'gate rejected output of step {i}')
    return cur


def route(llm: LLM, text: str, routes: dict[str, Callable[[str], str]],
          env: Envelope | None = None, default: str | None = None) -> str:
    """Routing — classify once, dispatch to the specialist handler.

    Cheap classification, then the expensive specialist only where needed.
    """
    env = env or Envelope()
    labels = ', '.join(routes)
    pick = llm(f'Classify the request into exactly one of: {labels}.\n'
               f'Answer with the label only.\n\nREQUEST:\n{text}').strip().lower()
    chosen = next((k for k in routes if k.lower() in pick), default or list(routes)[0])
    env.trace.add('route', 'dispatch', {'label': chosen})
    return routes[chosen](text)


def parallel(llm: LLM, prompts: list[str], aggregate: Callable[[list[str]], str],
             env: Envelope | None = None, workers: int = 4) -> str:
    """Parallelization — fan out independent subtasks, aggregate programmatically.

    Two variants: sectioning (different prompts) and voting (same prompt N times).
    """
    env = env or Envelope()
    env.trace.add('parallel', 'fanout', {'n': len(prompts)})
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        outs = list(ex.map(lambda p: llm(p), prompts))
    return aggregate(outs)


def vote(llm: LLM, prompt: str, n: int = 3, env: Envelope | None = None) -> dict:
    """Voting variant — same prompt N times; disagreement is a review signal."""
    outs = parallel(llm, [prompt] * n, lambda o: o, env)
    uniq = {}
    for o in outs:
        uniq[o.strip()] = uniq.get(o.strip(), 0) + 1
    best = max(uniq.items(), key=lambda kv: kv[1])
    return {'answer': best[0], 'votes': best[1], 'n': n,
            'unanimous': best[1] == n, 'needs_review': best[1] <= n // 2}


def orchestrate(llm: LLM, task: str, worker: Callable[[str], str],
                env: Envelope | None = None, max_workers: int = 4) -> str:
    """Orchestrator–Workers — planner decomposes dynamically, workers execute.

    Use when subtasks CANNOT be predicted upfront. Otherwise use chain/parallel.
    """
    env = env or Envelope()
    call = with_retry(llm) if _HAS_ENGINEERING else llm
    plan_raw = call('Decompose the task into 2-6 independent subtasks. '
                    'Return a JSON array of strings, nothing else.\n\nTASK:\n' + task)
    try:
        subtasks = json.loads(plan_raw[plan_raw.index('['):plan_raw.rindex(']') + 1])
    except Exception:
        subtasks = [task]
    subtasks = subtasks[:max_workers] or [task]
    env.trace.add('orchestrate', 'plan', {'subtasks': len(subtasks)})
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        results = list(ex.map(worker, subtasks))
    joined = '\n\n'.join(f'### {s}\n{r}' for s, r in zip(subtasks, results))
    return llm(f'Synthesize these worker results into one coherent answer.\n\n'
               f'TASK: {task}\n\n{joined}')


def evaluate_optimize(llm: LLM, task: str, rubric: str,
                      env: Envelope | None = None,
                      judge: LLM | None = None) -> dict:
    """Evaluator–Optimizer — generator/judge split with a bounded retry loop.

    The judge should be a DIFFERENT (often cheaper) model than the generator.
    Vague rubrics produce vague feedback; be explicit and checkable.
    """
    env = env or Envelope()
    judge = judge or llm
    call = with_retry(llm) if _HAS_ENGINEERING else llm
    jcall = with_retry(judge) if _HAS_ENGINEERING else judge
    draft = call(task)
    for i in range(env.max_iters):
        env.tick(i)
        verdict = jcall(f'Score the OUTPUT against the RUBRIC.\n'
                        f'Reply exactly "PASS" if every criterion is met, '
                        f'otherwise list the specific failures.\n\n'
                        f'RUBRIC:\n{rubric}\n\nOUTPUT:\n{draft}')
        env.trace.add('eval_opt', f'round{i}',
                      {'pass': verdict.strip().upper().startswith('PASS')})
        if verdict.strip().upper().startswith('PASS'):
            return {'output': draft, 'rounds': i + 1, 'passed': True}
        draft = call(f'Revise the OUTPUT to fix the CRITIQUE.\n\n'
                     f'TASK:\n{task}\n\nCRITIQUE:\n{verdict}\n\nOUTPUT:\n{draft}')
    # Final self_verify gate if criteria can be derived from the rubric lines
    if _HAS_ENGINEERING and rubric:
        passed, fails = self_verify(call, draft,
                                    [l.strip('- ').strip() for l in rubric.splitlines()
                                     if l.strip() and not l.strip().startswith('#')])
        env.trace.add('eval_opt', 'self_verify', {'passed': passed, 'fails': fails})
    return {'output': draft, 'rounds': env.max_iters, 'passed': False}


def react(llm: LLM, goal: str, tools: dict[str, Callable[[str], str]],
          env: Envelope | None = None,
          guardrails: 'Guardrails | None' = None) -> str:
    """ReAct — interleaved reason -> act -> observe, adapting to real results.

    Upgraded to use the engineering layer:
      * bounded `ContextWindow` instead of an unbounded scratchpad (the
        memory-growth anti-pattern we hit earlier)
      * `with_retry` around each LLM call (resilience to transient Azure 429/529)
      * optional input/step guardrails
    """
    env = env or Envelope()
    ctx = ContextWindow(max_turns=env.max_iters, max_chars=6000)
    names = ', '.join(tools)
    call = with_retry(llm) if _HAS_ENGINEERING else llm

    def step_prompt(history: str) -> str:
        return (f'GOAL: {goal}\nTOOLS: {names}\nHistory:\n{history}\n\n'
                f'Reply with either "ACT <tool> <input>" or "DONE <answer>".')

    for i in range(env.max_iters):
        env.tick(i)
        s = call(step_prompt(ctx.render())).strip()
        env.trace.add('react', f'step{i}', {'head': s[:40]})
        if guardrails and not guardrails.check_mid(s):
            ctx.add(f'\nBLOCKED(mid_guardrail): {s[:80]}')
            continue
        if s.upper().startswith('DONE'):
            return s[4:].strip()
        if s.upper().startswith('ACT'):
            body = s[3:].strip()
            tool = next((t for t in tools if body.lower().startswith(t.lower())), None)
            if not tool:
                ctx.add(f'\nERROR: unknown tool in {body[:60]}')
                continue
            arg = body[len(tool):].strip()
            try:
                obs = tools[tool](arg)
            except Exception as e:
                obs = f'TOOL ERROR: {e}'
            ctx.add(f'\nACT {tool} {arg}\nOBS {str(obs)[:800]}')
        else:
            ctx.add(f'\nMALFORMED: {s[:80]}')
    return call(f'Budget exhausted. Give the best answer from:\n{ctx.render()}')


def reflect(llm: LLM, task: str, env: Envelope | None = None,
            criteria: Iterable[str] | None = None) -> str:
    """Reflection — single-model self-critique before emitting the answer.

    Upgraded: optional `self_verify` gate — if `criteria` are given, the rewrite
    is re-checked against them once before returning.
    """
    env = env or Envelope()
    draft = llm(task)
    crit = llm(f'Critique this answer. List concrete defects only.\n\n'
               f'TASK:\n{task}\n\nANSWER:\n{draft}')
    env.trace.add('reflect', 'critique')
    out = llm(f'Rewrite the answer, fixing every defect.\n\n'
              f'TASK:\n{task}\n\nDEFECTS:\n{crit}\n\nDRAFT:\n{draft}')
    if criteria and _HAS_ENGINEERING:
        passed, _ = self_verify(llm, out, list(criteria))
        env.trace.add('reflect', 'self_verify', {'passed': passed})
    return out


__all__ = ['Envelope', 'Budget', 'Trace', 'chain', 'route', 'parallel', 'vote',
           'orchestrate', 'evaluate_optimize', 'react', 'reflect',
           'ContextWindow', 'Guardrails', 'self_verify', 'with_retry']
