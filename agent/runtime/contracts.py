from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[2]
TASK_ROOT = PurePosixPath("agent/tasks")
PROTECTED_PREFIXES = (
    PurePosixPath(".git"),
    PurePosixPath(".github"),
    PurePosixPath("agent/runtime"),
    PurePosixPath("agent/companion"),
)
MAX_EDIT_FILES = 12
MAX_FILE_BYTES = 250_000


def _relative_repo_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts or "." in path.parts:
        raise ValueError(f"unsafe repository path: {value!r}")
    return path


def _under(path: PurePosixPath, prefix: PurePosixPath) -> bool:
    return path == prefix or prefix in path.parents


def load_task(task_file: str | Path) -> tuple[Path, dict]:
    raw = PurePosixPath(str(task_file))
    if raw.is_absolute() or ".." in raw.parts or not _under(raw, TASK_ROOT):
        raise ValueError("task file must live under agent/tasks/")
    absolute = REPO_ROOT / Path(*raw.parts)
    task = json.loads(absolute.read_text())
    validate_task(task)
    return absolute, task


def validate_task(task: dict) -> None:
    required = {"id", "title", "objective", "acceptance_criteria", "context_files", "editable_files", "test_commands"}
    missing = required - set(task)
    if missing:
        raise ValueError(f"task missing fields: {sorted(missing)}")
    for field in ("id", "title", "objective"):
        if not isinstance(task[field], str) or not task[field].strip():
            raise ValueError(f"{field} must be non-empty text")
    criteria = task["acceptance_criteria"]
    if not isinstance(criteria, list) or not criteria or not all(isinstance(x, str) and x.strip() for x in criteria):
        raise ValueError("acceptance_criteria must be a non-empty list of text")
    context_files = task["context_files"]
    editable_files = task["editable_files"]
    if not isinstance(context_files, list) or not isinstance(editable_files, list) or not editable_files:
        raise ValueError("context_files must be a list and editable_files must be non-empty")
    if len(editable_files) > MAX_EDIT_FILES or len(editable_files) != len(set(editable_files)):
        raise ValueError("invalid editable_files collection")
    for value in context_files:
        path = _relative_repo_path(value)
        if not (REPO_ROOT / Path(*path.parts)).is_file():
            raise ValueError(f"missing context file: {value}")
    for value in editable_files:
        path = _relative_repo_path(value)
        if any(_under(path, prefix) for prefix in PROTECTED_PREFIXES):
            raise ValueError(f"protected path is not editable: {value}")
    commands = task["test_commands"]
    if not isinstance(commands, list) or not commands:
        raise ValueError("test_commands must be non-empty")
    for command in commands:
        if not isinstance(command, list) or not command or not all(isinstance(arg, str) and arg for arg in command):
            raise ValueError("each test command must be a non-empty argv list")


def validate_proposal(task: dict, proposal: dict) -> list[dict]:
    if not isinstance(proposal, dict):
        raise ValueError("proposal must be an object")
    changes = proposal.get("changes")
    if not isinstance(changes, list) or not changes or len(changes) > MAX_EDIT_FILES:
        raise ValueError("proposal changes are invalid")
    allowed = set(task["editable_files"])
    seen: set[str] = set()
    normalized = []
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError("each change must be an object")
        path = change.get("path")
        content = change.get("content")
        if path not in allowed or path in seen:
            raise ValueError(f"path not allowed or duplicated: {path!r}")
        _relative_repo_path(path)
        if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError(f"invalid content for {path}")
        seen.add(path)
        normalized.append({"path": path, "content": content})
    return normalized


def extract_json_object(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("response contains no JSON object")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("response JSON must be an object")
    return value
