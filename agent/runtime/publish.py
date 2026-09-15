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
        raise SystemExit("private publication command failed")
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--verification", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--base", default="main")
    parser.add_argument("--existing-branch")
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--result")
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

    checked(["git", "config", "user.name", "github-actions[bot]"])
    checked(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])

    if args.existing_branch:
        if not args.pr_number:
            raise SystemExit("existing branch publication requires PR number")
        current = checked(["git", "branch", "--show-current"])
        if current != args.existing_branch:
            raise SystemExit("repair publication is not on the expected branch")
        branch = args.existing_branch
    else:
        run_id = os.environ.get("GITHUB_RUN_ID", "local")
        slug = re.sub(r"[^a-z0-9-]+", "-", task["id"].lower()).strip("-")[:48]
        branch = f"agent/{slug}-{run_id}"
        checked(["git", "checkout", "-b", branch])

    checked(["git", "add", "--", *changed])
    checked(["git", "commit", "-m", f"agent: {task['title']}"])
    checked(["git", "push", "--set-upstream", "origin", branch])

    if args.existing_branch:
        result_record = {"branch": branch, "pull_request_number": args.pr_number, "updated": True}
    else:
        env = os.environ.copy()
        env["GH_TOKEN"] = env.get("GH_TOKEN") or env.get("GITHUB_TOKEN", "")
        body = f"Automated bounded task proposal.\n\nTask: `{task['id']}` — {task['title']}\nDeterministic verification: passed\nIndependent review: passed\n"
        created = subprocess.run(
            ["gh", "pr", "create", "--base", args.base, "--head", branch, "--title", f"agent: {task['title']}", "--body", body],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        if created.returncode != 0:
            raise SystemExit("private pull request publication failed")
        result_record = {"branch": branch, "pull_request": created.stdout.strip(), "updated": False}

    if args.result:
        result_path = Path(args.result)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result_record))
    else:
        print(json.dumps({"published": True}))


if __name__ == "__main__":
    main()
