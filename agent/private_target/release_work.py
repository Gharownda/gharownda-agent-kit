from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", required=True)
    args = parser.parse_args()

    work_path = Path(args.work)
    if not work_path.is_file():
        return
    work = json.loads(work_path.read_text())
    lease = work.get("lease_ref")
    if not lease:
        return
    repo = os.environ["TARGET_REPOSITORY"]
    encoded = str(lease).replace("/", "%2F")
    subprocess.run(
        ["gh", "api", "--method", "DELETE", f"repos/{repo}/git/refs/heads/{encoded}"],
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )


if __name__ == "__main__":
    main()
