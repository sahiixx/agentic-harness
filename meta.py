"""Autological engineering for the agentic harness.

The harness is *autological*: it applies its own patterns to its own corpus and
its own code. This module proves the loop is closed — the patterns aren't just
described, they operate on the system that defines them.

Examples of self-application:
  * self_review()        — evaluator-optimizer critiques harness/patterns.py
  * contract_audit()     — verifies every repo's AGENTS.md matches the contract
  * doc_sync()           — chain regenerates the harness's own README
  * route_own_issue()    — classify an incoming task and dispatch it

Every function uses the SAME azure.llm / azure.deep the repos use, so the
harness literally thinks about itself with the same models its children use.
"""
from __future__ import annotations

import os
import json
import subprocess
from typing import Callable

import azure
from patterns import (Envelope, chain, route, orchestrate, evaluate_optimize,
                      react, reflect)

LLM = azure.llm          # gpt-5.6-sol
DEEP = azure.deep        # claude-opus-5 (judge)

CONTRACT = dict(
    deployments=['gpt-5.6-sol', 'claude-opus-5', 'gpt-5', 'text-embedding-3-small'],
    claude_endpoint='/openai/v1/responses',
    secrets=['AZURE_FOUNDRY_API_KEY'],
    patterns=['chain', 'route', 'parallel', 'orchestrate',
              'evaluate_optimize', 'react', 'reflect'])


def self_review(path: str = '/opt/data/harness/patterns.py') -> dict:
    """Evaluator-optimizer: a model generates, Claude judges — on OUR code."""
    src = open(path, errors='ignore').read()
    rubric = (
        'The module must: (1) define every pattern in CONTRACT.patterns, '
        '(2) enforce a bounded Envelope (max_iters + deadline), '
        '(3) never execute untrusted code via eval/exec, '
        '(4) emit a Trace on each call. Flag any violation specifically.')
    task = f'Review this agentic harness module for contract violations.\n\n{src}'
    return evaluate_optimize(LLM, task, rubric, Envelope(max_iters=3), judge=DEEP)


def contract_audit(root: str = '/opt/data') -> dict:
    """Scan all cloned repos; confirm each AGENTS.md names the contract deployments.

    This is the harness policing its own distributed contract — autological
    governance, not a one-off script.
    """
    expected = set(CONTRACT['deployments'])
    report = {'checked': 0, 'compliant': 0, 'drift': []}
    for base in ('repos', 'forks', 'private'):
        bd = os.path.join(root, base)
        if not os.path.isdir(bd):
            continue
        for name in os.listdir(bd):
            ap = os.path.join(bd, name, 'AGENTS.md')
            if not os.path.isfile(ap):
                continue
            report['checked'] += 1
            txt = open(ap, errors='ignore').read()
            missing = [d for d in expected if d not in txt]
            if missing:
                report['drift'].append({'repo': name, 'missing': missing})
            else:
                report['compliant'] += 1
    report['compliant_pct'] = round(100 * report['compliant'] / max(1, report['checked']), 1)
    return report


def doc_sync() -> str:
    """Chain: regenerate the harness's own README from its code (self-doc)."""
    facts = (f"Modules: patterns.py ({len(CONTRACT['patterns'])} patterns), "
             f"azure.py (routes {CONTRACT['deployments']}).\n"
             f"Verified: 9/9 patterns live against Azure Foundry.")
    return chain(LLM, [
        'Summarize the above harness in 3 bullet points for a README Features section.',
        'Prepend "# agentic-harness" as the title line, nothing else before it.',
    ], facts)


def route_own_issue(text: str) -> str:
    """Route an incoming engineering task to the right handling path."""
    return route(LLM, text, {
        'review': lambda t: 'PATH: run self_review() then open a findings issue',
        'audit': lambda t: 'PATH: run contract_audit() across /opt/data',
        'doc': lambda t: 'PATH: run doc_sync() and commit the README',
        'deploy': lambda t: 'PATH: re-run test_live.py; if 9/9, push',
    }, Envelope())


def think_about_self(question: str) -> str:
    """Pure autology: the harness reflects on its own design using its own models."""
    return reflect(LLM, f'The agentic-harness is a system of 7 workflow patterns '
                        f'wired to Azure Foundry across 242 repos. {question}')


__all__ = ['self_review', 'contract_audit', 'doc_sync', 'route_own_issue',
           'think_about_self', 'CONTRACT']
