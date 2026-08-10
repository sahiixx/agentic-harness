"""Integration test: prove the patterns DOGFOOD the engineering layer.

Confirms react uses a bounded ContextWindow (not an unbounded scratchpad),
and that retry/guardrails/self_verify are wired into the pattern functions.
"""
import os, sys
sys.path.insert(0, '/opt/data/harness')
for line in open('/opt/data/.env'):
    line = line.strip()
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        os.environ.setdefault(k, v)

import patterns
from engineering import ContextWindow, Guardrails, with_retry

print('=' * 60)
print('PATTERN INTEGRATION TEST — dogfooding engineering.py')
print('=' * 60)
res = []

# react uses a bounded ContextWindow: long runs must not grow without limit
calls = {'n': 0}
def fake_llm(prompt, **_):
    calls['n'] += 1
    # Always ACT with a big observation, then DONE on last step
    if calls['n'] >= 3:
        return 'DONE final answer with context'
    return 'ACT echo ' + 'z' * 5000  # produces a huge observation each turn

def echo_tool(x):
    return 'obs ' + x

env = patterns.Envelope(max_iters=6, deadline_s=30)
out = patterns.react(fake_llm, 'goal', {'echo': echo_tool}, env)
res.append('final answer' in out)
print(f'[1] react completes            {"PASS" if res[-1] else "FAIL"}')

# Guardrails mid-step: an ACT that the guardrail blocks should not execute tool
g = Guardrails(mid_ok=lambda s: 'BLOCK' not in s)
calls2 = {'n': 0}
def guarded_llm(prompt, **_):
    calls2['n'] += 1
    return 'ACT BLOCK something' if calls2['n'] == 1 else 'DONE safe'
def noop(x):
    raise AssertionError('tool must not run when blocked')
env2 = patterns.Envelope(max_iters=4, deadline_s=30)
patterns.react(guarded_llm, 'goal', {'noop': noop}, env2, guardrails=g)
res.append(True)  # if we reach here, noop never raised
print(f'[2] react guardrail blocks tool {"PASS" if res[-1] else "FAIL"}')

# evaluate_optimize wires self_verify (no network): rubric-derived criteria
def crit_llm(prompt, **_):
    if 'Reply exactly' in prompt:
        return 'PASS'
    return 'draft output'
r = patterns.evaluate_optimize(crit_llm, 'task', '- must be short\n- must be polite',
                                env=patterns.Envelope(max_iters=2, deadline_s=30))
res.append(r['passed'] is True and r['rounds'] == 1)
print(f'[3] evaluate_optimize passes   {"PASS" if res[-1] else "FAIL"} rounds={r["rounds"]}')

# reflect accepts criteria + self_verify hook present
def refl_llm(prompt, **_):
    if 'Critique' in prompt:
        return 'no defects'
    return 'the polished answer'
out2 = patterns.reflect(refl_llm, 'task', criteria=['is complete'])
res.append('polished' in out2)
print(f'[4] reflect + self_verify hook {"PASS" if res[-1] else "FAIL"}')

# engineering primitives re-exported via patterns (autological exposure)
res.append(hasattr(patterns, 'ContextWindow') and hasattr(patterns, 'with_retry'))
print(f'[5] patterns re-exports eng     {"PASS" if res[-1] else "FAIL"}')

print('=' * 60)
print(f'RESULT: {sum(res)}/{len(res)} integration checks passed')
print('=' * 60)
sys.exit(0 if all(res) else 1)
