"""Live verification of meta-cognitive agent against Azure Foundry."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
for line in open('/opt/data/.env'):
    line=line.strip()
    if '=' in line and not line.startswith('#'):
        k,v=line.split('=',1); os.environ.setdefault(k,v)
import azure
from patterns import Trace
from metacognition import (MetaCognitiveAgent,CognitionBudget,calibrate,inspect_trace,Strategy)

results=[]
hi=calibrate(agreement=1,verifier=True,evidence_count=3)
lo=calibrate(agreement=0,verifier=False,tool_errors=2,contradictions=1)
results.append(hi>0.8 and lo<0.2)
print('[1] calibration', 'PASS' if results[-1] else 'FAIL', hi, lo)
tr=Trace(); tr.add('react','step0'); tr.add('react','tool_error',{'error':'timeout'})
ti=inspect_trace(tr); results.append(ti['events']==2 and ti['errors']==1)
print('[2] trace introspection', 'PASS' if results[-1] else 'FAIL', ti)
agent=MetaCognitiveAgent(azure.llm,judge=azure.deep,
    budget=CognitionBudget(max_model_calls=12,max_wall_s=480))
state=agent.solve('Design a robust retry policy with explicit bounds, idempotency, jitter, and dead-letter path.',
    rubric='Must include max attempts, exponential jitter, idempotency key, retry classification, timeout, circuit breaker, dead-letter queue.')
results.append(len(state.answer)>100 and 0<=state.confidence<=1 and agent.budget.calls<=12)
print('[3] live meta-solve', 'PASS' if results[-1] else 'FAIL', state.strategy.value,state.confidence,state.verifier_passed,agent.budget.calls)
encoded=json.dumps(state.report()); results.append('confidence' in encoded and 'needs_escalation' in encoded)
print('[4] auditable report', 'PASS' if results[-1] else 'FAIL',len(encoded))
print('RESULT:',sum(results),'/',len(results))
sys.exit(0 if all(results) else 1)
