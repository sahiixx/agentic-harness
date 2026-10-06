"""Live test of the autological meta layer — genuine self-application calls."""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

import meta
print('=' * 60)
print('AUTOLOGICAL HARNESS TEST — harness applies patterns to ITSELF')
print('=' * 60)

print('\n[1] contract_audit (local scan, no net)')
workspace_root = os.environ.get('HERMES_WORKSPACE_ROOT', str(REPO_ROOT.parent))
rep = meta.contract_audit(workspace_root)
print(f'    repos checked : {rep["checked"]}')
print(f'    compliant    : {rep["compliant"]} ({rep["compliant_pct"]}%)')
print(f'    drift        : {len(rep["drift"])} repos')

print('\n[2] self_review (LLM generates, claude-opus-5 judges)')
r = meta.self_review(str(REPO_ROOT / 'patterns.py'))
print(f'    passed={r["passed"]} rounds={r["rounds"]}')

print('\n[3] route_own_issue (routing pattern on itself)')
for q in ['We should audit all repos for secret drift',
          'Regenerate the harness docs',
          'Review patterns.py for eval() usage']:
    print(f'    {q[:38]:40s} -> {meta.route_own_issue(q)}')

print('\n[4] doc_sync (prompt-chain self-doc)')
d = meta.doc_sync()
print(f'    generated {len(d)} chars; title: {d.splitlines()[0]!r}')

print('\n' + '=' * 60)
print('AUTOLOGICAL LOOP CLOSED')
print('=' * 60)
