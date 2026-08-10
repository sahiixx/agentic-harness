"""Meta-cognition layer for the agentic harness.

First-order cognition answers a task. Second-order cognition monitors HOW the
answer was produced: uncertainty, strategy fit, evidence quality, failure mode,
and whether further work is worth the cost.

This module makes that loop explicit and machine-checkable:

    task -> select strategy -> execute -> introspect trace -> calibrate
         -> revise strategy (if warranted) -> emit answer + epistemic report

Not "an LLM saying it is confident": confidence is grounded in independent
signals — agreement, verifier outcome, evidence count, tool errors, budget use.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Callable, Any

from patterns import (Envelope, Trace, Budget, chain, route, parallel, vote,
                      orchestrate, evaluate_optimize, react, reflect)

LLM = Callable[..., str]


class Strategy(str, Enum):
    DIRECT = 'direct'
    CHAIN = 'chain'
    VOTE = 'vote'
    ORCHESTRATE = 'orchestrate'
    EVALUATE = 'evaluate_optimize'
    REACT = 'react'
    REFLECT = 'reflect'


@dataclass
class EpistemicState:
    """Structured beliefs about the current answer — not hidden chain-of-thought."""
    answer: str = ''
    strategy: Strategy = Strategy.DIRECT
    confidence: float = 0.0       # calibrated [0,1], from observable signals
    uncertainty: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    tool_errors: int = 0
    verifier_passed: bool | None = None
    iterations: int = 0
    trace: list[dict] = field(default_factory=list)

    @property
    def needs_escalation(self) -> bool:
        return (self.confidence < 0.70 or bool(self.contradictions)
                or self.tool_errors > 0 or self.verifier_passed is False)

    def report(self) -> dict:
        d = asdict(self)
        d['strategy'] = self.strategy.value
        d['needs_escalation'] = self.needs_escalation
        return d


@dataclass
class CognitionBudget:
    """Cost-aware cap for second-order reasoning."""
    max_model_calls: int = 12
    max_wall_s: float = 300.0
    calls: int = 0
    started: float = field(default_factory=time.time)

    def spend(self, n: int = 1):
        self.calls += n
        if self.calls > self.max_model_calls:
            raise Budget(f'metacognition call budget {self.max_model_calls} exceeded')
        if time.time() - self.started > self.max_wall_s:
            raise Budget(f'metacognition wall budget {self.max_wall_s}s exceeded')


# ---------------------------------------------------------------- calibration

def calibrate(*, agreement: float = 0.5, verifier: bool | None = None,
              evidence_count: int = 0, tool_errors: int = 0,
              contradictions: int = 0, budget_fraction: float = 0.0) -> float:
    """Calibrate confidence from observable signals, never self-reported certainty.

    Weights are deliberately conservative. The verifier is strongest; model
    agreement helps but cannot dominate (multiple models can share a mistake).
    """
    c = 0.20
    c += 0.25 * max(0.0, min(1.0, agreement))
    c += 0.30 if verifier is True else (-0.25 if verifier is False else 0.0)
    c += 0.15 * min(evidence_count / 3.0, 1.0)
    c -= 0.12 * min(tool_errors, 3)
    c -= 0.18 * min(contradictions, 3)
    c -= 0.10 * max(0.0, min(1.0, budget_fraction))
    return round(max(0.0, min(1.0, c)), 3)


# ----------------------------------------------------------- strategy selection

def select_strategy(llm: LLM, task: str, budget: CognitionBudget) -> Strategy:
    """Meta-controller chooses the least-complex strategy that fits the task."""
    budget.spend()
    labels = ', '.join(s.value for s in Strategy)
    prompt = f"""Select the simplest adequate strategy for this task.
Choices: {labels}
Rules:
- direct: factual/simple, no tools
- chain: known ordered steps
- vote: ambiguity/high variance, no tools
- orchestrate: unknown decomposition across independent specialists
- evaluate_optimize: clear quality rubric, iterative refinement valuable
- react: adaptive tool use required
- reflect: one draft benefits from self-critique
Reply with one choice only.

TASK: {task}"""
    raw = llm(prompt).strip().lower()
    for s in Strategy:
        if s.value in raw:
            return s
    return Strategy.REFLECT  # conservative fallback; not direct


# --------------------------------------------------------------- introspection

def inspect_trace(trace: Trace | list[dict]) -> dict:
    """Programmatic introspection of execution — no LLM, no self-deception."""
    events = trace.events if isinstance(trace, Trace) else trace
    errors = [e for e in events if any(x in str(e).lower()
                                      for x in ('error', 'reject', 'malformed'))]
    patterns = []
    for e in events:
        p = e.get('pattern', 'unknown')
        if p not in patterns:
            patterns.append(p)
    duration = 0.0
    if len(events) > 1:
        duration = round(events[-1].get('t', 0) - events[0].get('t', 0), 3)
    return {'events': len(events), 'errors': len(errors), 'patterns': patterns,
            'duration_s': duration, 'error_events': errors[:5]}


def extract_epistemics(llm: LLM, answer: str, task: str,
                       budget: CognitionBudget) -> dict:
    """Extract explicit evidence/assumptions/uncertainty — not chain-of-thought."""
    budget.spend()
    prompt = f"""Analyze the ANSWER's epistemic status. Do not reveal hidden reasoning.
Return valid JSON with exactly these arrays of short strings:
{{"evidence":[],"assumptions":[],"uncertainty":[],"contradictions":[]}}
Only include claims visible in the answer. Empty arrays are valid.

TASK: {task}
ANSWER: {answer}"""
    raw = llm(prompt)
    try:
        a, b = raw.index('{'), raw.rindex('}') + 1
        d = json.loads(raw[a:b])
        return {k: list(d.get(k, []))[:10]
                for k in ('evidence', 'assumptions', 'uncertainty', 'contradictions')}
    except Exception:
        return {'evidence': [], 'assumptions': [],
                'uncertainty': ['epistemic extraction failed'],
                'contradictions': []}


# -------------------------------------------------------------- main controller
class MetaCognitiveAgent:
    """Agent that monitors and adapts its own strategy.

    It emits both an answer and an EpistemicState. The state is auditable:
    confidence comes from observed signals, not model prose.
    """

    def __init__(self, llm: LLM, judge: LLM | None = None,
                 budget: CognitionBudget | None = None):
        self.llm = llm
        self.judge = judge or llm
        self.budget = budget or CognitionBudget()

    def _call(self, prompt: str) -> str:
        self.budget.spend()
        return self.llm(prompt)

    def solve(self, task: str, *, rubric: str | None = None,
              tools: dict[str, Callable[[str], str]] | None = None) -> EpistemicState:
        strategy = select_strategy(self.llm, task, self.budget)
        env = Envelope(max_iters=4, deadline_s=self.budget.max_wall_s)
        answer = ''
        agreement = 0.5
        verifier: bool | None = None

        if strategy == Strategy.DIRECT:
            answer = self._call(task)
        elif strategy == Strategy.CHAIN:
            answer = chain(self._call,
                           ['Identify the required sub-results.',
                            'Solve each sub-result.',
                            'Synthesize a concise final answer.'], task, env)
        elif strategy == Strategy.VOTE:
            self.budget.spend(3)
            v = vote(self.llm, task, n=3, env=env)
            answer = v['answer']
            agreement = v['votes'] / v['n']
        elif strategy == Strategy.ORCHESTRATE:
            self.budget.spend(3)
            answer = orchestrate(self.llm, task, self.llm, env, max_workers=3)
        elif strategy == Strategy.EVALUATE:
            self.budget.spend(2)
            r = evaluate_optimize(self.llm, task,
                                  rubric or 'Correct, complete, and directly addresses the task.',
                                  env, judge=self.judge)
            answer, verifier = r['output'], r['passed']
        elif strategy == Strategy.REACT:
            answer = react(self.llm, task, tools or {}, env)
        else:
            self.budget.spend(2)
            answer = reflect(self.llm, task, env)

        epi = extract_epistemics(self.llm, answer, task, self.budget)
        trace_info = inspect_trace(env.trace)
        state = EpistemicState(
            answer=answer, strategy=strategy,
            uncertainty=epi['uncertainty'], evidence=epi['evidence'],
            assumptions=epi['assumptions'], contradictions=epi['contradictions'],
            tool_errors=trace_info['errors'], verifier_passed=verifier,
            iterations=len(env.trace.events), trace=env.trace.events)
        state.confidence = calibrate(
            agreement=agreement, verifier=verifier,
            evidence_count=len(state.evidence), tool_errors=state.tool_errors,
            contradictions=len(state.contradictions),
            budget_fraction=self.budget.calls / self.budget.max_model_calls)

        # Second-order adaptation: low confidence gets ONE bounded escalation.
        if state.needs_escalation and self.budget.calls + 2 <= self.budget.max_model_calls:
            revised = evaluate_optimize(
                self.llm, f'Improve this answer to the task.\nTASK: {task}\nANSWER: {answer}',
                rubric or 'Correct, evidenced, explicit about uncertainty, directly useful.',
                Envelope(max_iters=2, deadline_s=self.budget.max_wall_s),
                judge=self.judge)
            self.budget.spend(2)
            state.answer = revised['output']
            state.verifier_passed = revised['passed']
            state.strategy = Strategy.EVALUATE
            state.confidence = calibrate(
                agreement=agreement, verifier=revised['passed'],
                evidence_count=len(state.evidence), tool_errors=state.tool_errors,
                contradictions=len(state.contradictions),
                budget_fraction=self.budget.calls / self.budget.max_model_calls)
        return state


__all__ = ['MetaCognitiveAgent', 'EpistemicState', 'CognitionBudget', 'Strategy',
           'calibrate', 'select_strategy', 'inspect_trace', 'extract_epistemics']
