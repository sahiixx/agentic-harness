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
    plan_raw = llm('Decompose the task into 2-6 independent subtasks. '
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
    draft = llm(task)
    for i in range(env.max_iters):
        env.tick(i)
        verdict = judge(f'Score the OUTPUT against the RUBRIC.\n'
                        f'Reply exactly "PASS" if every criterion is met, '
                        f'otherwise list the specific failures.\n\n'
                        f'RUBRIC:\n{rubric}\n\nOUTPUT:\n{draft}')
        env.trace.add('eval_opt', f'round{i}',
                      {'pass': verdict.strip().upper().startswith('PASS')})
        if verdict.strip().upper().startswith('PASS'):
            return {'output': draft, 'rounds': i + 1, 'passed': True}
        draft = llm(f'Revise the OUTPUT to fix the CRITIQUE.\n\n'
                    f'TASK:\n{task}\n\nCRITIQUE:\n{verdict}\n\nOUTPUT:\n{draft}')
    return {'output': draft, 'rounds': env.max_iters, 'passed': False}


def react(llm: LLM, goal: str, tools: dict[str, Callable[[str], str]],
          env: Envelope | None = None) -> str:
    """ReAct — interleaved reason -> act -> observe, adapting to real results."""
    env = env or Envelope()
    scratch = ''
    names = ', '.join(tools)
    for i in range(env.max_iters):
        env.tick(i)
        step = llm(f'GOAL: {goal}\nTOOLS: {names}\n'
                   f'History:\n{scratch}\n\n'
                   f'Reply with either "ACT <tool> <input>" or "DONE <answer>".')
        s = step.strip()
        env.trace.add('react', f'step{i}', {'head': s[:40]})
        if s.upper().startswith('DONE'):
            return s[4:].strip()
        if s.upper().startswith('ACT'):
            body = s[3:].strip()
            tool = next((t for t in tools if body.lower().startswith(t.lower())), None)
            if not tool:
                scratch += f'\nERROR: unknown tool in {body[:60]}'
                continue
            arg = body[len(tool):].strip()
            try:
                obs = tools[tool](arg)
            except Exception as e:
                obs = f'TOOL ERROR: {e}'
            scratch += f'\nACT {tool} {arg}\nOBS {str(obs)[:800]}'
        else:
            scratch += f'\nMALFORMED: {s[:80]}'
    return llm(f'Budget exhausted. Give the best answer from:\n{scratch}')


def reflect(llm: LLM, task: str, env: Envelope | None = None) -> str:
    """Reflection — single-model self-critique before emitting the answer."""
    env = env or Envelope()
    draft = llm(task)
    crit = llm(f'Critique this answer. List concrete defects only.\n\n'
               f'TASK:\n{task}\n\nANSWER:\n{draft}')
    env.trace.add('reflect', 'critique')
    return llm(f'Rewrite the answer, fixing every defect.\n\n'
               f'TASK:\n{task}\n\nDEFECTS:\n{crit}\n\nDRAFT:\n{draft}')


__all__ = ['Envelope', 'Budget', 'Trace', 'chain', 'route', 'parallel', 'vote',
           'orchestrate', 'evaluate_optimize', 'react', 'reflect']
