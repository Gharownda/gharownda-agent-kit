# Task manifests

Task manifests under `agent/tasks/` are checked-in contracts for bounded implementation work. They define the scope, acceptance criteria, and allowed changes for each task.

## Required Manifest Fields

Each task manifest must contain the following fields:

- `id`: A unique identifier for the task.
- `title`: A brief description of the task.
- `objective`: The goal of the task.
- `acceptance_criteria`: A list of criteria that must be met for the task to be considered complete.
- `context_files`: A list of files that provide context for the task but are not editable.
- `editable_files`: A list of files that may be edited as part of the task.
- `test_commands`: A list of commands used to verify the task's implementation.

## Purpose of context_files and editable_files

- `context_files`: These files provide the necessary context for the task but are not allowed to be modified. They are used to ensure that the worker has access to the required information to complete the task.
- `editable_files`: These files are the ones that the worker is allowed to modify as part of the task. They are explicitly listed to ensure that changes are made only within the allowed scope.

## Lifecycle

1. **Worker**: The worker implements the task by making changes to the files listed in `editable_files` and ensuring that the acceptance criteria are met.
2. **Verification**: The verification process runs the test commands specified in `test_commands` to ensure that the changes made by the worker are correct and meet the acceptance criteria.
3. **Reviewer**: The reviewer audits the verified candidate to ensure that all acceptance criteria are met, and that no changes were made outside the allowed scope.
4. **Maintainer**: The maintainer is responsible for merging the reviewed candidate into the repository and ensuring that the task is completed correctly.

## Example

```json
{
  "id": "document-task-contract",
  "title": "Document the task manifest format",
  "objective": "Expand docs/TASKS.md into a concise contributor reference for the task manifest format used by this repository.",
  "acceptance_criteria": [
    "Document the required manifest fields.",
    "Explain the purpose of context_files and editable_files.",
    "Explain the worker, verification, review, and maintainer lifecycle.",
    "Include a small JSON example consistent with the repository implementation.",
  ],
  "context_files": [
    "README.md",
    "AGENTS.md",
    "docs/GOVERNANCE.md"
  ],
  "editable_files": [
    "docs/TASKS.md"
  ],
  "test_commands": [
    ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
  ]
}
```