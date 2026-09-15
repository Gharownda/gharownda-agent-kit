from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


def run(argv: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, env=os.environ.copy(), text=True, capture_output=True, check=False)


def gh_json(args: list[str], *, cwd: Path) -> object:
    completed = run(["gh", *args], cwd=cwd)
    if completed.returncode != 0:
        raise RuntimeError("private target API query failed")
    return json.loads(completed.stdout or "null")


def task_catalog(root: Path) -> dict[str, tuple[str, dict]]:
    catalog: dict[str, tuple[str, dict]] = {}
    for path in sorted((root / "agent" / "tasks").glob("*.json")):
        task = json.loads(path.read_text())
        task_id = task.get("id")
        if isinstance(task_id, str) and task_id:
            catalog[task_id] = (path.relative_to(root).as_posix(), task)
    return catalog


def task_id_from_pr_body(body: str | None) -> str | None:
    match = re.search(r"Task:\s*`([^`]+)`", body or "")
    return match.group(1) if match else None


def has_trusted_change_request(pr: dict, trusted: set[str]) -> bool:
    for review in pr.get("reviews") or []:
        author = (review.get("author") or {}).get("login")
        if author in trusted and str(review.get("state", "")).upper() == "CHANGES_REQUESTED":
            return True
    return False


def has_failed_checks(pr: dict) -> bool:
    failed = {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "ERROR"}
    for check in pr.get("statusCheckRollup") or []:
        conclusion = str(check.get("conclusion") or check.get("state") or "").upper()
        if conclusion in failed:
            return True
    return False


def lease_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:24]


def active_leases(root: Path, repo: str) -> set[str]:
    completed = run(["gh", "api", f"repos/{repo}/git/matching-refs/heads/agent-lease/"], cwd=root)
    if completed.returncode != 0:
        raise RuntimeError("could not inspect private work leases")
    values = json.loads(completed.stdout or "[]")
    result = set()
    for item in values:
        ref = str(item.get("ref") or "")
        if ref.startswith("refs/heads/agent-lease/"):
            result.add(ref.rsplit("/", 1)[-1])
    return result


def claim(root: Path, repo: str, key: str) -> str | None:
    digest = lease_hash(key)
    ref = f"agent-lease/{digest}"
    base = run(["git", "rev-parse", "HEAD"], cwd=root)
    if base.returncode != 0:
        raise RuntimeError("could not resolve private target base")
    created = run(
        [
            "gh", "api", "--method", "POST", f"repos/{repo}/git/refs",
            "-f", f"ref=refs/heads/{ref}",
            "-f", f"sha={base.stdout.strip()}",
        ],
        cwd=root,
    )
    return ref if created.returncode == 0 else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(os.environ["AGENT_TARGET_ROOT"]).resolve()
    repo = os.environ["TARGET_REPOSITORY"]
    trusted = {item.strip() for item in os.environ.get("TRUSTED_REVIEWERS", "").split(",") if item.strip()}
    queue = json.loads((root / "agent" / "queue.json").read_text())
    catalog = task_catalog(root)
    leases = active_leases(root, repo)

    prs = gh_json(
        [
            "pr", "list", "--repo", repo, "--state", "open", "--limit", "100",
            "--json", "number,headRefName,body,reviews,statusCheckRollup",
        ],
        cwd=root,
    )
    if not isinstance(prs, list):
        raise RuntimeError("unexpected private PR response")

    open_task_ids: set[str] = set()
    candidates: list[dict] = []
    for pr in sorted(prs, key=lambda item: int(item.get("number", 0))):
        head = str(pr.get("headRefName") or "")
        if not head.startswith("agent/"):
            continue
        task_id = task_id_from_pr_body(pr.get("body"))
        if not task_id or task_id not in catalog:
            continue
        open_task_ids.add(task_id)
        if has_trusted_change_request(pr, trusted) or has_failed_checks(pr):
            task_file, task = catalog[task_id]
            if task.get("delegation") == "worker-with-review":
                candidates.append(
                    {
                        "kind": "repair",
                        "key": f"repair:{pr['number']}",
                        "task_id": task_id,
                        "task_file": task_file,
                        "pr_number": int(pr["number"]),
                        "head_ref": head,
                    }
                )

    for item in queue.get("tasks", []):
        if not item.get("enabled"):
            continue
        task_file = item.get("task_file")
        task_path = root / str(task_file)
        if not task_path.is_file():
            continue
        task = json.loads(task_path.read_text())
        task_id = task.get("id")
        if not isinstance(task_id, str) or task_id in open_task_ids:
            continue
        if task.get("delegation") != "worker-with-review":
            continue
        candidates.append({"kind": "new", "key": f"task:{task_id}", "task_id": task_id, "task_file": task_file})

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    for candidate in candidates:
        digest = lease_hash(candidate["key"])
        if digest in leases:
            continue
        lease_ref = claim(root, repo, candidate["key"])
        if lease_ref:
            candidate["lease_ref"] = lease_ref
            output.write_text(json.dumps(candidate))
            return

    output.write_text(json.dumps({"kind": "none"}))


if __name__ == "__main__":
    main()
