from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

TARGET_REPOSITORY = os.environ.get("TARGET_REPOSITORY", "Gharownda/gharownda-app")
MAX_PRIVATE_PRS = int(os.environ.get("MAX_PRIVATE_PRS", "5"))
MARKER_PREFIX = "<!-- public-maintainer-verification:"
COMMAND_TIMEOUT_SECONDS = 1800
COMMENT_CHUNK_SIZE = 55_000

COMMANDS = [
    ("Ruby dependencies", ["bundle", "install", "--jobs", "4", "--retry", "3"]),
    ("Frontend dependencies", ["npm", "ci"]),
    ("Prepare database", ["bin/rails", "db:drop", "db:create", "db:prepare"]),
    ("Seed database", ["bin/rails", "db:seed"]),
    ("Plan status", ["python", "scripts/plan_status.py", "--check"]),
    ("AI context", ["python", "scripts/check_ai_context.py"]),
    ("Rails specs", ["bundle", "exec", "rspec"]),
    ("Frontend typecheck", ["npm", "run", "typecheck"]),
    ("Frontend build", ["npm", "run", "build"]),
    ("Ruby lint", ["bundle", "exec", "rubocop"]),
    ("Rails security scan", ["bundle", "exec", "brakeman", "--no-pager"]),
    ("Ruby dependency audit", ["bundle", "exec", "bundler-audit", "check", "--update"]),
]

SECRET_PATTERNS = [
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]+"),
    re.compile(r"(?i)(authorization:\s*(?:bearer|basic)\s+)[^\s]+"),
]


def safe_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "TARGET_TOKEN"):
        env.pop(key, None)
    env["RAILS_ENV"] = "test"
    env.setdefault("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/gharownda_test")
    return env


def private_api(path: str, *, method: str = "GET", payload: dict | None = None) -> object:
    argv = ["gh", "api"]
    if method != "GET":
        argv.extend(["--method", method])
    argv.append(path)
    if payload is not None:
        argv.extend(["--input", "-"])
    completed = subprocess.run(
        argv,
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        capture_output=True,
        env=os.environ.copy(),
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"private GitHub API request failed: {path}")
    return json.loads(completed.stdout or "null")


def redact(value: str) -> str:
    result = value
    for pattern in SECRET_PATTERNS:
        if pattern.groups:
            result = pattern.sub(r"\1[REDACTED]", result)
        else:
            result = pattern.sub("[REDACTED]", result)
    return result


def already_verified(pr_number: int, head_sha: str) -> bool:
    comments = private_api(f"repos/{TARGET_REPOSITORY}/issues/{pr_number}/comments?per_page=100")
    marker = f"{MARKER_PREFIX}{head_sha} -->"
    return isinstance(comments, list) and any(marker in str(comment.get("body") or "") for comment in comments)


def clone_private_branch(branch: str, destination: Path) -> None:
    token = os.environ["GH_TOKEN"]
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env = safe_env()
    env.update(
        {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {auth}",
        }
    )
    completed = subprocess.run(
        ["git", "clone", "--quiet", "--depth", "1", "--branch", branch, f"https://github.com/{TARGET_REPOSITORY}", str(destination)],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("private branch checkout failed")


def run_command(root: Path, label: str, argv: list[str]) -> dict:
    try:
        completed = subprocess.run(
            argv,
            cwd=root,
            env=safe_env(),
            text=True,
            capture_output=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
        return {
            "label": label,
            "argv": argv,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "label": label,
            "argv": argv,
            "returncode": None,
            "timeout": True,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }


def report_text(head_sha: str, results: list[dict]) -> str:
    passed = all(result.get("returncode") == 0 for result in results)
    lines = [
        f"{MARKER_PREFIX}{head_sha} -->",
        "## Public maintainer verification",
        "",
        f"Result: **{'PASS' if passed else 'FAIL'}**",
        "",
        "This mirrors the private Application CI contract on an ephemeral public GitHub-hosted runner because the private job did not receive a runner. Credentials were removed from the test environment; evidence is posted only to this private pull request.",
        "",
    ]
    for result in results:
        status = "PASS" if result.get("returncode") == 0 else "FAIL"
        lines.extend(
            [
                f"### {status} — {result['label']}",
                "",
                f"Command: `{' '.join(result['argv'])}`",
                "",
                "```text",
                redact((result.get("stdout") or "") + (result.get("stderr") or "")),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def post_chunks(pr_number: int, text: str) -> None:
    chunks = [text[index : index + COMMENT_CHUNK_SIZE] for index in range(0, len(text), COMMENT_CHUNK_SIZE)] or [text]
    for index, chunk in enumerate(chunks, start=1):
        if len(chunks) > 1:
            chunk = f"Part {index}/{len(chunks)}\n\n{chunk}"
        private_api(
            f"repos/{TARGET_REPOSITORY}/issues/{pr_number}/comments",
            method="POST",
            payload={"body": chunk},
        )


def main() -> None:
    pulls = private_api(f"repos/{TARGET_REPOSITORY}/pulls?state=open&per_page=100")
    if not isinstance(pulls, list):
        raise SystemExit("unexpected private pull-request response")

    candidates = []
    for pull in pulls:
        head = pull.get("head") or {}
        branch = str(head.get("ref") or "")
        sha = str(head.get("sha") or "")
        if branch.startswith("maintainer/") and sha and not pull.get("draft"):
            candidates.append((int(pull["number"]), branch, sha))

    verified = 0
    failed = 0
    with tempfile.TemporaryDirectory(prefix="private-maintainer-verification-") as tmp:
        base = Path(tmp)
        for position, (pr_number, branch, head_sha) in enumerate(candidates[:MAX_PRIVATE_PRS]):
            if already_verified(pr_number, head_sha):
                continue
            root = base / f"candidate-{position}"
            clone_private_branch(branch, root)
            results = []
            for label, argv in COMMANDS:
                result = run_command(root, label, argv)
                results.append(result)
                if result.get("returncode") != 0:
                    break
            post_chunks(pr_number, report_text(head_sha, results))
            verified += 1
            if results and results[-1].get("returncode") != 0:
                failed += 1
            shutil.rmtree(root, ignore_errors=True)

    print(f"Private maintainer verification completed for {verified} candidate(s); failures={failed}.")


if __name__ == "__main__":
    main()
