from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from contracts import REPO_ROOT, load_task, validate_proposal

TEST_TIMEOUT_SECONDS = 180


def run(command: list[str]) -> dict:
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, timeout=TEST_TIMEOUT_SECONDS, check=False)
    return {"argv": command, "returncode": completed.returncode, "elapsed_ms": round((time.perf_counter() - started) * 1000), "stdout": completed.stdout[-8000:], "stderr": completed.stderr[-8000:]}


def ensure_safe_write_target(target: Path) -> None:
    root = REPO_ROOT.resolve()
    resolved = target.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise RuntimeError(f"editable path resolves outside repository: {target}")
    if target.is_symlink():
        raise RuntimeError(f"editable path must not be a symlink: {target}")


def restore_editable_files(task: dict) -> None:
    paths = task["editable_files"]
    subprocess.run(["git", "reset", "-q", "HEAD", "--", *paths], cwd=REPO_ROOT, check=False)
    for rel in paths:
        tracked = subprocess.run(
            ["git", "cat-file", "-e", f"HEAD:{rel}"],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode == 0
        target = REPO_ROOT / rel
        if tracked:
            subprocess.run(["git", "checkout", "HEAD", "--", rel], cwd=REPO_ROOT, check=True)
        elif target.exists() or target.is_symlink():
            if not target.is_file() and not target.is_symlink():
                raise RuntimeError(f"editable path is not a file: {rel}")
            target.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--worker-record", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--patch", required=True)
    args = parser.parse_args()
    _, task = load_task(args.task)
    worker = json.loads(Path(args.worker_record).read_text())
    if worker.get("task_id") != task["id"] or not worker.get("valid"):
        raise SystemExit("worker record does not match trusted task")
    changes = validate_proposal(task, worker["proposal"])
    restore_editable_files(task)
    for change in changes:
        target = REPO_ROOT / change["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        ensure_safe_write_target(target)
        target.write_text(change["content"])
    subprocess.run(["git", "add", "-N", "--", *[c["path"] for c in changes]], cwd=REPO_ROOT, check=False)
    diff = subprocess.run(["git", "diff", "--no-ext-diff", "--", *[c["path"] for c in changes]], cwd=REPO_ROOT, text=True, capture_output=True, check=True).stdout
    if not diff.strip():
        raise SystemExit("proposal produced no repository diff")
    results = []
    passed = True
    failed_test_index = None
    failed_returncode = None
    for index, command in enumerate(task["test_commands"]):
        try:
            result = run(command)
        except subprocess.TimeoutExpired:
            result = {"argv": command, "returncode": None, "elapsed_ms": TEST_TIMEOUT_SECONDS * 1000, "timeout": True, "stdout": "", "stderr": ""}
        results.append(result)
        if result.get("returncode") != 0:
            passed = False
            failed_test_index = index
            failed_returncode = result.get("returncode")
            break
    report = {
        "task_id": task["id"],
        "changed_files": [c["path"] for c in changes],
        "tests_passed": passed,
        "tests": results,
        "failed_test_index": failed_test_index,
        "failed_returncode": failed_returncode,
        "worker_summary": worker["proposal"].get("summary"),
        "worker_risks": worker["proposal"].get("risks", []),
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2))
    Path(args.patch).write_text(diff)
    if not passed:
        print(f"verification stage {failed_test_index} failed with return code {failed_returncode}")
        raise SystemExit("proposal failed deterministic verification")


if __name__ == "__main__":
    main()
