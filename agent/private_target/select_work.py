from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

MAX_REPAIR_ATTEMPTS = 2
LEASE_TTL = timedelta(hours=6)
LEASE_MESSAGE_PREFIX = "bounded agent work lease:"


def run(argv: list[str], *, cwd: Path, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=os.environ.copy(),
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


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


def delete_ref(root: Path, repo: str, ref: str) -> None:
    run(["gh", "api", "--method", "DELETE", f"repos/{repo}/git/refs/heads/{ref}"], cwd=root)


def active_leases(root: Path, repo: str) -> set[str]:
    completed = run(["gh", "api", f"repos/{repo}/git/matching-refs/heads/agent-lease/"], cwd=root)
    if completed.returncode != 0:
        raise RuntimeError("could not inspect private work leases")
    values = json.loads(completed.stdout or "[]")
    now = datetime.now(timezone.utc)
    active: set[str] = set()

    for item in values:
        full_ref = str(item.get("ref") or "")
        prefix = "refs/heads/agent-lease/"
        if not full_ref.startswith(prefix):
            continue
        digest = full_ref.removeprefix(prefix)
        commit_sha = str((item.get("object") or {}).get("sha") or "")
        if not commit_sha:
            active.add(digest)
            continue

        commit_response = run(["gh", "api", f"repos/{repo}/git/commits/{commit_sha}"], cwd=root)
        if commit_response.returncode != 0:
            active.add(digest)
            continue
        commit = json.loads(commit_response.stdout)
        message = str(commit.get("message") or "")
        committed_at = str((commit.get("committer") or {}).get("date") or "")
        if not message.startswith(LEASE_MESSAGE_PREFIX) or not committed_at:
            active.add(digest)
            continue

        lease_time = datetime.fromisoformat(committed_at.replace("Z", "+00:00"))
        if now - lease_time > LEASE_TTL:
            delete_ref(root, repo, f"agent-lease/{digest}")
        else:
            active.add(digest)

    return active


def claim(root: Path, repo: str, key: str) -> str | None:
    digest = lease_hash(key)
    ref = f"agent-lease/{digest}"
    base = run(["git", "rev-parse", "HEAD"], cwd=root)
    if base.returncode != 0:
        raise RuntimeError("could not resolve private target base")
    base_sha = base.stdout.strip()

    base_commit = run(["gh", "api", f"repos/{repo}/git/commits/{base_sha}"], cwd=root)
    if base_commit.returncode != 0:
        raise RuntimeError("could not inspect private target base commit")
    tree_sha = str((json.loads(base_commit.stdout).get("tree") or {}).get("sha") or "")
    if not tree_sha:
        raise RuntimeError("private target base commit has no tree")

    payload = json.dumps(
        {
            "message": f"{LEASE_MESSAGE_PREFIX} {digest}",
            "tree": tree_sha,
            "parents": [base_sha],
            "committer": {
                "name": "gharownda-agent-kit",
                "email": "41898282+github-actions[bot]@users.noreply.github.com",
                "date": datetime.now(timezone.utc).isoformat(),
            },
        }
    )
    lease_commit = run(
        ["gh", "api", "--method", "POST", f"repos/{repo}/git/commits", "--input", "-"],
        cwd=root,
        input_text=payload,
    )
    if lease_commit.returncode != 0:
        raise RuntimeError("could not create private work lease commit")
    lease_sha = str(json.loads(lease_commit.stdout).get("sha") or "")
    if not lease_sha:
        raise RuntimeError("private work lease commit has no SHA")

    created = run(
        [
            "gh", "api", "--method", "POST", f"repos/{repo}/git/refs",
            "-f", f"ref=refs/heads/{ref}",
            "-f", f"sha={lease_sha}",
        ],
        cwd=root,
    )
    return ref if created.returncode == 0 else None


def repair_attempts(root: Path, repo: str, head: str) -> int:
    encoded_head = quote(head, safe="")
    completed = run(["gh", "api", f"repos/{repo}/compare/main...{encoded_head}"], cwd=root)
    if completed.returncode != 0:
        return MAX_REPAIR_ATTEMPTS
    total_commits = int(json.loads(completed.stdout).get("total_commits") or 0)
    return max(0, total_commits - 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(os.environ["AGENT_TARGET_ROOT"]).resolve()
    repo = os.environ["TARGET_REPOSITORY"]
    trusted = {item.strip() for item in os.environ.get("TRUSTED_REVIEWERS", "").split(",") if item.strip()}
    queue = json.loads((root / "agent" / "queue.json").read_text())
    if int(queue.get("max_parallel", 0)) > 5:
        raise RuntimeError("private queue exceeds public worker slot limit")
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
        task_id = task_id_from_pr_body(pr.get("body"))
        if task_id and task_id in catalog:
            open_task_ids.add(task_id)

        head = str(pr.get("headRefName") or "")
        if not task_id or task_id not in catalog or not head.startswith("agent/"):
            continue
        if not (has_trusted_change_request(pr, trusted) or has_failed_checks(pr)):
            continue
        task_file, task = catalog[task_id]
        if task.get("delegation") != "worker-with-review":
            continue
        attempts = repair_attempts(root, repo, head)
        if attempts >= MAX_REPAIR_ATTEMPTS:
            continue
        candidates.append(
            {
                "kind": "repair",
                "key": f"repair:{pr['number']}",
                "task_id": task_id,
                "task_file": task_file,
                "pr_number": int(pr["number"]),
                "head_ref": head,
                "repair_attempt": attempts + 1,
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
