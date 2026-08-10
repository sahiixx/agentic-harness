"""Live verification of the engineering primitives + retry resilience."""
import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(__file__) or '/opt/data/harness')
for line in open('/opt/data/.env'):
    line = line.strip()
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        os.environ.setdefault(k, v)

import azure
from engineering import (with_retry, Guardrails, ContextWindow, WorkingMemory,
                         semantic_route, self_verify, TransientError)

results = []
calls = {'n': 0}
def flaky():
    calls['n'] += 1
    if calls['n'] < 3:
        raise TransientError('simulated 429')
    return 'recovered'
wrapped = with_retry(flaky, attempts=4, base=0.01)
out = wrapped()
results.append(out == 'recovered' and calls['n'] == 3)
print(f'[1] with_retry recovers      {"PASS" if results[-1] else "FAIL"}  calls={calls["n"]}')

def always_fail():
    raise TransientError('529')
try:
    with_retry(always_fail, attempts=2, base=0.01)()
    results.append(False)
except TransientError:
    results.append(True)
print(f'[2] retry exhausts+raises   {"PASS" if results[-1] else "FAIL"}')

g = Guardrails()
results.append(g.check_input('hello') and not g.check_input('x' * 300000))
results.append(g.check_output('result') and not g.check_output(''))
print(f'[3] guardrails 3-layer       {"PASS" if results[-2] and results[-1] else "FAIL"}')

cw = ContextWindow(max_turns=4, max_chars=400)
for i in range(20):
    cw.add(f'turn {i}: ' + 'x' * 60)
results.append(len(cw) <= 4 and cw.chars <= 400)
print(f'[4] context bounded         {"PASS" if results[-1] else "FAIL"}  turns={len(cw)} chars={cw.chars}')

tmpf = tempfile.mktemp(suffix='.json')
WorkingMemory(tmpf).put('goal', 'build resilient agent')
results.append(WorkingMemory(tmpf).get('goal') == 'build resilient agent')
os.unlink(tmpf)
print(f'[5] working memory persists  {"PASS" if results[-1] else "FAIL"}')

routes = {'billing': 'I was charged twice and need a refund',
          'technical': 'the API returns 500 on every POST request',
          'greeting': 'hello how are you today'}
rank = semantic_route(azure.embed, 'my server is down with a 503 error', routes, top_k=1)
results.append(rank[0][0] == 'technical')
print(f'[6] semantic route (live)    {"PASS" if results[-1] else "FAIL"}  -> {rank[0]}')

ok, fails = self_verify(azure.llm, 'The answer is 42.',
                        ['contains a number', 'is a complete sentence'])
results.append(ok and not fails)
print(f'[7] self_verify gate         {"PASS" if results[-1] else "FAIL"}  passed={ok} fails={fails}')

txt = azure.complete('Reply with the single word: PONG')
results.append('PONG' in txt)
print(f'[8] azure.complete+retry     {"PASS" if results[-1] else "FAIL"}  -> {txt.strip()!r}')

print(f'RESULT: {sum(results)}/{len(results)} engineering checks verified')
sys.exit(0 if all(results) else 1)
