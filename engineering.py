"""Agentic engineering primitives — the capabilities the harness documented but
never implemented. Each closes a gap we hit in production:

1. Context engineering  — bounded, compressed, isolated working memory
2. Retry/backoff        — Azure throws 429/529; chat completions need resilience
3. Guardrail layering   — validate at input, mid-loop, and output
4. Semantic routing     — embeddings-based dispatch (not keyword-only)
5. Working memory       — persistent store across calls within a session
6. Self-verification     — programmatic gate any pattern can use

All are dependency-light, observable, and tested live against Azure.
"""
from __future__ import annotations

import time
import re
import json
import hashlib
import os
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence


# ----------------------------------------------------------------- retries
class TransientError(Exception):
    """Raised when a call fails in a way that may succeed on retry (429/529/5xx)."""


BACKOFF_CODES = {429, 500, 502, 503, 504}


def with_retry(fn: Callable[..., str], *, attempts: int = 4, base: float = 1.0,
               jitter: float = 0.5) -> Callable[..., str]:
    """Wrap an LLM call with exponential backoff + jitter.

    The wrapped fn must raise TransientError (or any Exception) on failure.
    We treat a set of HTTP-ish codes as retryable; callers raise TransientError
    when they see them. This is exactly the resilience Azure's flaky 429/529
    rate limits demand.
    """
    def wrapped(*a, **k):
        last = None
        for i in range(attempts):
            try:
                return fn(*a, **k)
            except TransientError as e:
                last = e
                if i == attempts - 1:
                    break
                sleep = base * (2 ** i) + (jitter * i)
                time.sleep(min(sleep, 8.0))
        raise last or RuntimeError('retry exhausted')
    wrapped.__name__ = getattr(fn, '__name__', 'wrapped')
    return wrapped


# ----------------------------------------------------------------- guardrails
@dataclass
class Guardrails:
    """Three-layer validation. A layer returns True if input is allowed."""
    input_ok: Callable[[str], bool] = lambda s: bool(s and len(s) < 200000)
    mid_ok: Callable[[str], bool] = lambda s: True
    output_ok: Callable[[str], bool] = lambda s: bool(s and len(s) < 200000)

    def check_input(self, s: str) -> bool:
        return bool(self.input_ok(s))

    def check_mid(self, s: str) -> bool:
        return bool(self.mid_ok(s))

    def check_output(self, s: str) -> bool:
        return bool(self.output_ok(s))


# ----------------------------------------------------------------- context
class ContextWindow:
    """Bounded, compressing working memory.

    The anti-pattern we hit: ReAct scratchpads grow unbounded (we truncated at
    800 chars, losing information). This keeps a rolling window of the N most
    recent turns and a compact summary, never exceeding `max_chars`.
    """

    def __init__(self, max_turns: int = 8, max_chars: int = 6000):
        self.max_turns = max_turns
        self.max_chars = max_chars
        self._turns: list[str] = []

    def add(self, turn: str) -> None:
        self._turns.append(turn[-self.max_chars // self.max_turns:])
        if len(self._turns) > self.max_turns:
            # summarize oldest half into one compressed line
            keep = self._turns[self.max_turns // 2:]
            old = self._turns[:self.max_turns // 2]
            summary = f'[compressed {len(old)} prior turns] ' + ' | '.join(
                o[:80] for o in old)
            self._turns = [summary] + keep

    def render(self) -> str:
        return '\n'.join(self._turns)

    @property
    def chars(self) -> int:
        return sum(len(t) for t in self._turns)

    def __len__(self) -> int:
        return len(self._turns)


# ----------------------------------------------------------------- memory
class WorkingMemory:
    """Persistent key/value store for an agent session (in-memory; file-backed)."""

    def __init__(self, path: str | None = None):
        self._store: dict[str, str] = {}
        self._path = path
        if path and os.path.exists(path):
            try:
                self._store = json.load(open(path))
            except Exception:
                self._store = {}

    def put(self, k: str, v: str) -> None:
        self._store[k] = v
        self._flush()

    def get(self, k: str, default: str = '') -> str:
        return self._store.get(k, default)

    def has(self, k: str) -> bool:
        return k in self._store

    def _flush(self) -> None:
        if self._path:
            json.dump(self._store, open(self._path, 'w'))


# ----------------------------------------------------------------- semantic route
def semantic_route(embed: Callable[[str], list], text: str,
                   routes: dict[str, str], top_k: int = 1) -> list[tuple[str, float]]:
    """Embedding-based routing. Unlike keyword `route`, this dispatches on meaning.

    `routes` maps label -> representative example text. We embed the incoming
    text and each example, then return the labels with highest cosine similarity.
    """
    q = embed(text)[0] if isinstance(embed(text), list) and embed(text) and \
        isinstance(embed(text)[0], list) else embed(text)
    scored = []
    for label, example in routes.items():
        e = embed(example)
        e = e[0] if (e and isinstance(e[0], list)) else e
        scored.append((label, _cosine(q, e)))
    scored.sort(key=lambda x: -x[1])
    return scored[:top_k]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


# ----------------------------------------------------------------- self-verify
def self_verify(llm: Callable[..., str], output: str,
                criteria: Sequence[str]) -> tuple[bool, list[str]]:
    """Programmatic self-verification gate any pattern can call.

    Returns (passed, failures). Each criterion is checked by the model as a
    yes/no; we parse the answer, never trust a self-reported confidence score.
    """
    fails = []
    for c in criteria:
        prompt = (f'Does the OUTPUT satisfy this criterion? Answer only YES or NO.\n'
                  f'CRITERION: {c}\n\nOUTPUT:\n{output}')
        ans = llm(prompt).strip().upper()
        if not ans.startswith('YES'):
            fails.append(c)
    return (len(fails) == 0, fails)


__all__ = ['TransientError', 'with_retry', 'Guardrails', 'ContextWindow',
           'WorkingMemory', 'semantic_route', 'self_verify']
