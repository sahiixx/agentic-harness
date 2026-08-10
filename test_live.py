"""Live end-to-end test of the agentic harness against Azure Foundry.

This is a real execution test: every pattern makes real model calls.
"""
import sys, os
sys.path.insert(0, '/opt/data/harness')

for line in open('/opt/data/.env'):
    line = line.strip()
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        os.environ.setdefault(k, v)

import azure
from patterns import (Envelope, chain, route, parallel, vote, orchestrate,
                      evaluate_optimize, react, reflect)

llm = azure.llm
results = {}

print('=' * 62)
print('LIVE HARNESS TEST — real Azure Foundry calls')
print('=' * 62)

# 1. chain
try:
    env = Envelope(max_iters=4, deadline_s=240)
    out = chain(llm, ['Extract the single key noun. Reply with one word.',
                      'Reply with that word in uppercase, nothing else.'],
                'The quick brown fox jumps over the lazy dog.', env)
    ok = out.strip().isupper() and len(out.strip()) < 40
    results['chain'] = ok
    print(f'[1] chain            {"PASS" if ok else "FAIL"}  -> {out.strip()[:40]!r}')
except Exception as e:
    results['chain'] = False
    print('[1] chain            FAIL ', str(e)[:70])

# 2. route
try:
    env = Envelope()
    out = route(llm, 'My server returns HTTP 500 on every POST.',
                {'billing': lambda t: 'BILLING_HANDLER',
                 'technical': lambda t: 'TECH_HANDLER'}, env)
    ok = out == 'TECH_HANDLER'
    results['route'] = ok
    print(f'[2] route            {"PASS" if ok else "FAIL"}  -> {out}')
except Exception as e:
    results['route'] = False
    print('[2] route            FAIL ', str(e)[:70])

# 3. parallel
try:
    env = Envelope()
    out = parallel(llm, ['Reply with exactly: ALPHA',
                         'Reply with exactly: BETA',
                         'Reply with exactly: GAMMA'],
                   lambda outs: '|'.join(o.strip() for o in outs), env)
    ok = all(w in out.upper() for w in ('ALPHA', 'BETA', 'GAMMA'))
    results['parallel'] = ok
    print(f'[3] parallel         {"PASS" if ok else "FAIL"}  -> {out[:50]!r}')
except Exception as e:
    results['parallel'] = False
    print('[3] parallel         FAIL ', str(e)[:70])

# 4. vote
try:
    v = vote(llm, 'What is 17 + 25? Reply with the number only.', n=3)
    ok = '42' in v['answer']
    results['vote'] = ok
    print(f'[4] vote             {"PASS" if ok else "FAIL"}  -> {v["answer"][:20]!r} '
          f'votes={v["votes"]}/{v["n"]} unanimous={v["unanimous"]}')
except Exception as e:
    results['vote'] = False
    print('[4] vote             FAIL ', str(e)[:70])

# 5. orchestrate
try:
    env = Envelope(max_iters=3, deadline_s=300)
    out = orchestrate(llm, 'Describe a REST API for a todo app in 3 short bullets.',
                      lambda s: llm('One sentence only: ' + s), env, max_workers=3)
    ok = len(out.strip()) > 40
    results['orchestrate'] = ok
    print(f'[5] orchestrate      {"PASS" if ok else "FAIL"}  -> {len(out)} chars, '
          f'{len(env.trace.events)} trace events')
except Exception as e:
    results['orchestrate'] = False
    print('[5] orchestrate      FAIL ', str(e)[:70])

# 6. evaluator-optimizer  (generator=sol, judge=claude — different models)
try:
    env = Envelope(max_iters=3, deadline_s=300)
    r = evaluate_optimize(
        llm,
        'Write a Python function is_prime(n) with a docstring and type hints.',
        'Must: (1) be valid Python, (2) have type hints, (3) have a docstring, '
        '(4) handle n<2 correctly.',
        env, judge=azure.deep)
    ok = r['passed']
    results['evaluate_optimize'] = ok
    print(f'[6] evaluator-opt    {"PASS" if ok else "FAIL"}  -> passed={r["passed"]} '
          f'rounds={r["rounds"]} (judge=claude-opus-5)')
except Exception as e:
    results['evaluate_optimize'] = False
    print('[6] evaluator-opt    FAIL ', str(e)[:70])

# 7. react
try:
    env = Envelope(max_iters=4, deadline_s=240)
    calls = {'n': 0}

    def calc(x):
        # Safe arithmetic: parse the AST and evaluate only numeric operators.
        # No eval() — arbitrary code cannot execute here.
        import ast as _ast
        import operator as _op
        _OPS = {_ast.Add: _op.add, _ast.Sub: _op.sub, _ast.Mult: _op.mul,
                _ast.Div: _op.truediv, _ast.Pow: _op.pow, _ast.Mod: _op.mod,
                _ast.USub: _op.neg, _ast.UAdd: _op.pos}

        def ev(node):
            if isinstance(node, _ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, _ast.BinOp) and type(node.op) in _OPS:
                return _OPS[type(node.op)](ev(node.left), ev(node.right))
            if isinstance(node, _ast.UnaryOp) and type(node.op) in _OPS:
                return _OPS[type(node.op)](ev(node.operand))
            raise ValueError('unsupported expression')

        calls['n'] += 1
        return str(ev(_ast.parse(x.strip(), mode='eval').body))

    out = react(llm, 'Compute 123 * 456 using the calc tool, then report the number.',
                {'calc': calc}, env)
    ok = '56088' in out
    results['react'] = ok
    print(f'[7] react            {"PASS" if ok else "FAIL"}  -> tool_calls={calls["n"]} '
          f'answer={out.strip()[:30]!r}')
except Exception as e:
    results['react'] = False
    print('[7] react            FAIL ', str(e)[:70])

# 8. reflect
try:
    env = Envelope()
    out = reflect(llm, 'State in one sentence why bounded execution matters for agents.', env)
    ok = len(out.strip()) > 25
    results['reflect'] = ok
    print(f'[8] reflect          {"PASS" if ok else "FAIL"}  -> {len(out)} chars')
except Exception as e:
    results['reflect'] = False
    print('[8] reflect          FAIL ', str(e)[:70])

# 9. budget enforcement (must raise)
try:
    from patterns import Budget
    env = Envelope(max_iters=1)
    try:
        chain(llm, ['a', 'b', 'c'], 'x', env)
        results['budget'] = False
        print('[9] budget guard     FAIL  (did not raise)')
    except Budget:
        results['budget'] = True
        print('[9] budget guard     PASS  (Budget raised as designed)')
except Exception as e:
    results['budget'] = False
    print('[9] budget guard     FAIL ', str(e)[:70])

print('=' * 62)
p = sum(1 for v in results.values() if v)
print(f'RESULT: {p}/{len(results)} patterns verified live')
print('=' * 62)
sys.exit(0 if p == len(results) else 1)
