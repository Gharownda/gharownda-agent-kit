from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path


def load_contracts(target_root: Path):
    os.environ["AGENT_TARGET_ROOT"] = str(target_root.resolve())
    module_path = Path(__file__).resolve().parent / "runtime" / "contracts.py"
    spec = importlib.util.spec_from_file_location("gharownda_agent_kit_contracts", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Agent Kit contract runtime")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command_validate_task(args: argparse.Namespace) -> int:
    contracts = load_contracts(Path(args.target_root))
    _, task = contracts.load_task(args.task)
    print(json.dumps({
        "valid": True,
        "task_id": task["id"],
        "editable_files": len(task["editable_files"]),
        "context_files": len(task["context_files"]),
        "test_commands": len(task["test_commands"]),
    }, sort_keys=True))
    return 0


def command_validate_proposal(args: argparse.Namespace) -> int:
    contracts = load_contracts(Path(args.target_root))
    _, task = contracts.load_task(args.task)
    proposal = json.loads(Path(args.proposal).read_text(encoding="utf-8"))
    changes = contracts.validate_proposal(task, proposal)
    print(json.dumps({
        "valid": True,
        "task_id": task["id"],
        "changed_files": [change["path"] for change in changes],
    }, sort_keys=True))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="gak",
        description="Validate bounded Agent Kit tasks and proposals locally.",
    )
    root.add_argument(
        "--target-root",
        default=".",
        help="repository root that owns agent/tasks and task context (default: current directory)",
    )
    commands = root.add_subparsers(dest="command", required=True)

    validate_task = commands.add_parser("validate-task", help="validate one task manifest and its context")
    validate_task.add_argument("task", help="task path under agent/tasks/")
    validate_task.set_defaults(handler=command_validate_task)

    validate_proposal = commands.add_parser("validate-proposal", help="validate a JSON candidate against a task allow-list")
    validate_proposal.add_argument("task", help="task path under agent/tasks/")
    validate_proposal.add_argument("proposal", help="JSON proposal file")
    validate_proposal.set_defaults(handler=command_validate_proposal)

    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return args.handler(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise SystemExit(f"gak: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
