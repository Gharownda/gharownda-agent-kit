from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from contracts import REPO_ROOT, load_task


def checked(argv: list[str]) -> str:
    result = subprocess.run(argv, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise SystemExit(result.stderr[-4000:] or result.stdout[-4000:])
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--verification", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--base", default="main")
    args = parser.parse_args()
    _, task = load_task(args.task)
    verification = json.loads(Path(args.verification).read_text())
    review = json.loads(Path(args.review).read_text())
    if verification.get("task_id") != task["id"] or not verification.get("tests_passed"):
        raise SystemExit("publish requires passing verification")
    if review.get("task_id") != task["id"] or review.get("verdict") != "pass":
        raise SystemExit("publish requires reviewer pass")
    changed = verification.get("changed_files", [])
    if not changed or any(path not in set(task["editable_files"]) for path in changed):
        raise SystemExit("changed file set is invalid")

    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    slug = re.sub(r"[^a-z0-9-]+", "-", task["id"].lower()).strip("-")[:48]
    branch = f"agent/{slug}-{run_id}"
    checked(["git", "config", "user.name", "github-actions[bot]"])
    checked(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
    checked(["git", "checkout", "-b", branch])
    checked(["git", "add", "--", *changed])
    checked(["git", "commit", "-m", f"agent: {task['title']}"])
    checked(["git", "push", "--set-upstream", "origin", branch])

    env = os.environ.copy()
    env["GH_TOKEN"] = env.get("GH_TOKEN") or env.get("GITHUB_TOKEN", "")
    body = f"Automated bounded task proposal.\n\nTask: `{task['id']}` — {task['title']}\nDeterministic verification: passed\nIndependent review: passed\n"
    result = subprocess.run(["gh", "pr", "create", "--base", args.base, "--head", branch, "--title", f"agent: {task['title']}", "--body", body], cwd=REPO_ROOT, text=True, capture_output=True, env=env, check=False)
    print(json.dumps({"branch": branch, "pull_request": result.stdout.strip() if result.returncode == 0 else None, "pr_error": result.stderr.strip() if result.returncode else None}, indent=2))


if __name__ == "__main__":
    main()
