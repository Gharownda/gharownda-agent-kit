from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

COMMENT_CHUNK = 45_000
DIAGNOSTIC_PATHS = (
    "/tmp/work.json",
    "/tmp/worker.json",
    "/tmp/worker-repair-1.json",
    "/tmp/worker-repair-2.json",
    "/tmp/worker-review-repair.json",
    "/tmp/review.json",
    "/tmp/verification.json",
    "/tmp/candidate.patch",
    "/tmp/feedback.json",
)

TOKEN_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*(?:bearer|token|basic)\s+)[^\s]+"),
    re.compile(r"(?i)\b(?:github_pat_|ghp_|gho_|ghu_|ghs_|ghr_)[A-Za-z0-9_]+\b"),
)
DATABASE_URL_PATTERN = re.compile(r"(?i)(postgres(?:ql)?://[^:\s/@]+:)([^@\s]+)(@)")
GENERIC_SECRET_PATTERN = re.compile(
    r"(?i)(\b(?:token|password|secret|api[_-]?key)\b\s*[=:]\s*)([^\s\"']+)"
)


def redact(text: str) -> str:
    value = text
    value = DATABASE_URL_PATTERN.sub(r"\1[REDACTED]\3", value)
    value = TOKEN_PATTERNS[0].sub(r"\1[REDACTED]", value)
    value = TOKEN_PATTERNS[1].sub("[REDACTED_TOKEN]", value)
    value = GENERIC_SECRET_PATTERN.sub(r"\1[REDACTED]", value)
    return value


def chunks(text: str, limit: int = COMMENT_CHUNK) -> list[str]:
    if not text:
        return [""]
    return [text[index : index + limit] for index in range(0, len(text), limit)]


def api_request(token: str, method: str, url: str, payload: dict | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "gharownda-agent-kit",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {url} failed with {exc.code}: {detail[:1000]}") from exc


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_task(work: dict, target_root: Path) -> dict:
    task_file = work.get("task_file")
    if not isinstance(task_file, str) or not task_file:
        return {"id": "unknown-task", "title": "Unknown private task"}
    path = target_root / task_file
    if not path.is_file():
        return {"id": Path(task_file).stem, "title": Path(task_file).stem}
    task = read_json(path)
    return {
        "id": str(task.get("id") or Path(task_file).stem),
        "title": str(task.get("title") or task.get("id") or Path(task_file).stem),
    }


def diagnostic_files() -> list[Path]:
    paths = [Path(path) for path in DIAGNOSTIC_PATHS]
    diagnostics = Path("/tmp/diagnostics")
    if diagnostics.is_dir():
        paths.extend(sorted(path for path in diagnostics.iterdir() if path.is_file()))
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen or not path.is_file():
            continue
        seen.add(key)
        result.append(path)
    return result


def issue_for_task(token: str, repository: str, marker: str, title: str, body: str) -> dict:
    issues_url = f"https://api.github.com/repos/{repository}/issues?state=open&per_page=100"
    issues = api_request(token, "GET", issues_url) or []
    for issue in issues:
        if issue.get("pull_request"):
            continue
        if marker in (issue.get("body") or ""):
            return issue
    return api_request(
        token,
        "POST",
        f"https://api.github.com/repos/{repository}/issues",
        {"title": title, "body": body},
    )


def existing_run_marker(token: str, repository: str, issue_number: int, marker: str) -> bool:
    page = 1
    while True:
        url = f"https://api.github.com/repos/{repository}/issues/{issue_number}/comments?per_page=100&page={page}"
        comments = api_request(token, "GET", url) or []
        if any(marker in (comment.get("body") or "") for comment in comments):
            return True
        if len(comments) < 100:
            return False
        page += 1


def add_comment(token: str, repository: str, issue_number: int, body: str) -> None:
    api_request(
        token,
        "POST",
        f"https://api.github.com/repos/{repository}/issues/{issue_number}/comments",
        {"body": body},
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", default="/tmp/work.json")
    parser.add_argument("--repository", default=os.environ.get("TARGET_REPOSITORY"))
    parser.add_argument("--target-root", default=os.environ.get("AGENT_TARGET_ROOT"))
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise SystemExit("GH_TOKEN is required for private diagnostics")
    if not args.repository:
        raise SystemExit("target repository is required")
    if not args.target_root:
        raise SystemExit("target root is required")

    work_path = Path(args.work)
    if not work_path.is_file():
        raise SystemExit("private work record is unavailable")
    work = read_json(work_path)
    task = load_task(work, Path(args.target_root))

    task_id = task["id"]
    task_title = task["title"]
    issue_marker = f"<!-- agent-diagnostic:{task_id} -->"
    run_id = os.environ.get("GITHUB_RUN_ID", "unknown")
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "unknown")
    job = os.environ.get("GITHUB_JOB", "worker")
    run_marker = f"<!-- agent-run:{run_id}:{run_attempt}:{job} -->"
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    source_repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_url = f"{server}/{source_repo}/actions/runs/{run_id}" if source_repo and run_id != "unknown" else "unavailable"

    issue = issue_for_task(
        token,
        args.repository,
        issue_marker,
        f"[Agent diagnostic] {task_id}: {task_title}",
        "\n".join(
            [
                issue_marker,
                f"Automated private diagnostics for `{task_id}` — **{task_title}**.",
                "",
                "This issue is intentionally stored in the private target repository. Public runner artifacts do not contain the private task evidence.",
                "Credentials and credential-like values are redacted before posting.",
            ]
        ),
    )
    issue_number = int(issue["number"])
    if existing_run_marker(token, args.repository, issue_number, run_marker):
        print(f"private diagnostic issue #{issue_number} already contains this run")
        return

    overview = redact(
        "\n".join(
            [
                run_marker,
                f"## Failed agent run {run_id} / attempt {run_attempt}",
                "",
                f"- Public coordinator run: {run_url}",
                f"- Job: `{job}`",
                f"- Work kind: `{work.get('kind', 'unknown')}`",
                f"- Task file: `{work.get('task_file', 'unknown')}`",
                f"- Existing PR: `{work.get('pr_number', 'n/a')}`",
                "",
                "The comments below contain every task-specific diagnostic file that remained on the ephemeral runner at failure time. Large files are split into sequential comments without truncation.",
            ]
        )
    )
    add_comment(token, args.repository, issue_number, overview)

    files = diagnostic_files()
    if not files:
        add_comment(token, args.repository, issue_number, "No task-specific diagnostic files were available on the runner.")
    for path in files:
        content = redact(path.read_text(errors="replace"))
        parts = chunks(content)
        for index, part in enumerate(parts, start=1):
            header = f"### `{path}`"
            if len(parts) > 1:
                header += f" — part {index}/{len(parts)}"
            add_comment(token, args.repository, issue_number, f"{header}\n\n```text\n{part}\n```")

    print(f"private diagnostic issue #{issue_number} updated")


if __name__ == "__main__":
    main()
