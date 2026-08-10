"""Azure Foundry client for the agentic harness.

Handles the one non-obvious routing rule: Claude deployments on Azure answer
only via the Responses API, everything else via chat/completions.
"""
from __future__ import annotations

import os
import json
import urllib.request

BASE = os.environ.get(
    'AZURE_FOUNDRY_BASE_URL',
    'https://admin-3443-resourche.openai.azure.com/openai/v1')
KEY = os.environ.get('AZURE_FOUNDRY_API_KEY', '')

DEFAULT = 'gpt-5.6-sol'
DEEP = 'claude-opus-5'
EMBED = 'text-embedding-3-small'

# Deployments that ONLY answer on /responses
RESPONSES_ONLY = ('claude',)


def _post(path: str, payload: dict, timeout: int = 180) -> dict:
    if not KEY:
        raise RuntimeError('AZURE_FOUNDRY_API_KEY is not set')
    req = urllib.request.Request(
        f'{BASE}{path}',
        data=json.dumps(payload).encode(),
        headers={'api-key': KEY, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def complete(prompt: str, *, model: str = DEFAULT, max_tokens: int = 4000,
             system: str | None = None) -> str:
    """Single completion. Routes Claude to /responses automatically."""
    if any(m in model.lower() for m in RESPONSES_ONLY):
        d = _post('/responses', {'model': model, 'input': prompt,
                                 'max_output_tokens': max_tokens})
        parts = []
        for o in d.get('output', []):
            for c in o.get('content', []) or []:
                if c.get('text'):
                    parts.append(c['text'])
        return '\n'.join(parts)
    msgs = ([{'role': 'system', 'content': system}] if system else []) + \
           [{'role': 'user', 'content': prompt}]
    d = _post('/chat/completions', {'model': model, 'messages': msgs,
                                    'max_completion_tokens': max_tokens})
    return d['choices'][0]['message'].get('content', '')


def embed(text: str | list[str], *, model: str = EMBED) -> list:
    d = _post('/embeddings', {'model': model, 'input': text})
    return [x['embedding'] for x in d['data']]


def llm(prompt: str, *, model: str | None = None) -> str:
    """Callable matching the harness LLM signature."""
    return complete(prompt, model=model or DEFAULT)


def deep(prompt: str, *, model: str | None = None) -> str:
    """Deep-reasoning callable (Claude via Responses API)."""
    return complete(prompt, model=model or DEEP)


__all__ = ['complete', 'embed', 'llm', 'deep', 'DEFAULT', 'DEEP', 'EMBED']
