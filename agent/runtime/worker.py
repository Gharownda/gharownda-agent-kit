from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from contracts import REPO_ROOT, extract_json_object, load_task, validate_proposal
from model import load_gguf

SYSTEM = """Act as a bounded implementation worker. Follow the task objective, acceptance criteria, editable-file list, and output schema supplied by the trusted runner. Return one JSON object with summary, changes, tests_expected, and risks. Each change must contain an allowed path and complete UTF-8 replacement content. If the task cannot be completed within its listed files, return no changes and explain the blocker in risks."""


def build_prompt(task: dict) -> str:
    sections = [
        "/no_think",
        f"Task ID: {task['id']}",
        f"Title: {task['title']}",
        f"Objective:\n{task['objective']}",
        "Acceptance criteria:",
        *[f"- {item}" for item in task["acceptance_criteria"]],
        "Editable files:",
        *[f"- {path}" for path in task["editable_files"]],
        "Verification commands:",
        *["- " + " ".join(command) for command in task["test_commands"]],
        "Repository context:",
    ]
    for rel in task["context_files"]:
        sections.extend([f"--- FILE: {rel} ---", (REPO_ROOT / rel).read_text(), f"--- END FILE: {rel} ---"])
    sections.append('Output schema: {"summary":"...","changes":[{"path":"...","content":"..."}],"tests_expected":["..."],"risks":["..."]}')
    return "\n".join(sections)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--model-key", default="qwen3-14b-q4")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    _, task = load_task(args.task)
    model_entry, llm = load_gguf(args.model_key)
    started = time.perf_counter()
    result = llm.create_chat_completion(
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": build_prompt(task)}],
        temperature=0,
        max_tokens=2400,
    )
    raw = (result["choices"][0]["message"]["content"] or "").strip()
    record = {"task_id": task["id"], "model": args.model_key, "model_entry": model_entry, "elapsed_ms": round((time.perf_counter() - started) * 1000), "raw": raw, "valid": False, "proposal": None, "error": None}
    try:
        proposal = extract_json_object(raw)
        validate_proposal(task, proposal)
        record["valid"] = True
        record["proposal"] = proposal
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2))
    if not record["valid"]:
        raise SystemExit("worker proposal failed contract validation")


if __name__ == "__main__":
    main()
