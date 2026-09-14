from __future__ import annotations

import argparse
import json
from pathlib import Path

from contracts import extract_json_object, load_task
from model import load_gguf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--patch", required=True)
    parser.add_argument("--verification", required=True)
    parser.add_argument("--model-key", default="qwen3-14b-q4")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    _, task = load_task(args.task)
    verification = json.loads(Path(args.verification).read_text())
    if verification.get("task_id") != task["id"] or not verification.get("tests_passed"):
        raise SystemExit("review requires matching passing verification")

    _, llm = load_gguf(args.model_key)
    criteria = "\n".join(f"{i}. {item}" for i, item in enumerate(task["acceptance_criteria"], start=1))
    prompt = f"""/no_think
Evaluate the supplied implementation against each requirement independently.
Task: {task['title']}
Objective: {task['objective']}
Requirements:
{criteria}
Implementation diff:
{Path(args.patch).read_text()}
Verification result:
{json.dumps(verification, indent=2)}
Return one JSON object with keys requirement_checks, verdict, blocking_findings, non_blocking_findings, reason. Each requirement_checks item must contain criterion_index, satisfied, and evidence. verdict is pass or changes_required.
"""
    result = llm.create_chat_completion(messages=[{"role": "user", "content": prompt}], temperature=0.2, seed=42, max_tokens=1600)
    raw = (result["choices"][0]["message"]["content"] or "").strip()
    review = extract_json_object(raw)

    checks = review.get("requirement_checks")
    verdict = review.get("verdict")
    findings = review.get("blocking_findings")
    if not isinstance(checks, list) or verdict not in {"pass", "changes_required"} or not isinstance(findings, list):
        raise SystemExit("review output has an invalid structure")

    expected = set(range(1, len(task["acceptance_criteria"]) + 1))
    seen = set()
    all_satisfied = True
    for check in checks:
        index = check.get("criterion_index")
        if index not in expected or index in seen or not isinstance(check.get("satisfied"), bool) or not str(check.get("evidence", "")).strip():
            raise SystemExit("review requirement record is invalid")
        seen.add(index)
        all_satisfied = all_satisfied and check["satisfied"]
    if seen != expected:
        raise SystemExit("review did not cover every requirement")
    if verdict == "pass" and (findings or not all_satisfied):
        raise SystemExit("review pass is inconsistent with its evidence")

    record = {"task_id": task["id"], "model": args.model_key, "valid": True, "verdict": verdict, "review": review, "raw": raw}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2))
    if verdict != "pass":
        raise SystemExit("review requested changes")


if __name__ == "__main__":
    main()
