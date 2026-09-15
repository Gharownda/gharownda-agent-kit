from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr-number", required=True, type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    repo = os.environ["TARGET_REPOSITORY"]
    trusted = {item.strip() for item in os.environ.get("TRUSTED_REVIEWERS", "").split(",") if item.strip()}
    completed = subprocess.run(
        ["gh", "pr", "view", str(args.pr_number), "--repo", repo, "--json", "reviews,comments"],
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit("could not collect private PR feedback")
    value = json.loads(completed.stdout)
    feedback: list[str] = []
    for review in value.get("reviews") or []:
        author = (review.get("author") or {}).get("login")
        body = str(review.get("body") or "").strip()
        state = str(review.get("state") or "").upper()
        if author in trusted and body and state in {"CHANGES_REQUESTED", "COMMENTED"}:
            feedback.append(body)
    for comment in value.get("comments") or []:
        author = (comment.get("author") or {}).get("login")
        body = str(comment.get("body") or "").strip()
        if author in trusted and body:
            feedback.append(body)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(feedback[-8:]))


if __name__ == "__main__":
    main()
