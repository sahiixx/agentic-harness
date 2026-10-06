"""Deterministic verification for the harness and engineering layer.

This suite deliberately uses local callables and temporary files. Provider
verification lives in the explicit workflow_dispatch job instead.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

import meta
import patterns
from engineering import ContextWindow, Guardrails, WorkingMemory, self_verify, semantic_route
from metacognition import calibrate, inspect_trace


def main() -> None:
    def fake_llm(prompt: str, **_: object) -> str:
        if prompt.startswith("Classify"):
            return "technical"
        if prompt.startswith("Does the OUTPUT"):
            return "YES"
        if prompt.startswith("Score the OUTPUT"):
            return "PASS"
        return "local response"

    assert patterns.chain(fake_llm, ["step one", "step two"], "seed") == "local response"
    assert patterns.route(
        fake_llm,
        "the API returns 500",
        {"billing": lambda _: "billing", "technical": lambda _: "technical"},
    ) == "technical"

    calls = {"count": 0}

    def react_llm(_: str) -> str:
        calls["count"] += 1
        return "ACT echo local" if calls["count"] == 1 else "DONE local answer"

    assert patterns.react(react_llm, "echo locally", {"echo": lambda value: value}).strip() == "local answer"

    result = patterns.evaluate_optimize(
        fake_llm,
        "write a local answer",
        "- must be deterministic",
        patterns.Envelope(max_iters=2),
    )
    assert result["passed"] is True and result["rounds"] == 1

    guardrails = Guardrails()
    assert guardrails.check_input("hello")
    assert guardrails.check_output("result")
    window = ContextWindow(max_turns=3, max_chars=120)
    window.add("x" * 200)
    assert len(window) == 1 and window.chars <= 40

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "memory.json"
        WorkingMemory(str(path)).put("goal", "offline")
        assert WorkingMemory(str(path)).get("goal") == "offline"
        repo = Path(directory) / "repos" / "fixture"
        repo.mkdir(parents=True)
        (repo / "AGENTS.md").write_text(" ".join(meta.CONTRACT["deployments"]), encoding="utf-8")
        report = meta.contract_audit(directory)
        assert report["checked"] == 1 and report["compliant"] == 1

    assert self_verify(fake_llm, "a local sentence", ["is deterministic"])[0]
    assert semantic_route(
        lambda text: [[1.0, 0.0] if "technical" in text or "server" in text else [0.0, 1.0]],
        "the server is down",
        {"technical": "technical server", "billing": "billing invoice"},
    )[0][0] == "technical"

    trace = patterns.Trace()
    trace.add("offline", "check")
    assert inspect_trace(trace)["events"] == 1
    assert calibrate(agreement=1, verifier=True, evidence_count=2) > 0.8
    print("OFFLINE RESULT: deterministic harness checks passed")


if __name__ == "__main__":
    main()
