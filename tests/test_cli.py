from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTest(unittest.TestCase):
    def build_target(self, root: Path) -> tuple[Path, Path]:
        (root / "agent" / "tasks").mkdir(parents=True)
        (root / "docs").mkdir()
        (root / "docs" / "context.md").write_text("context", encoding="utf-8")
        task = {
            "id": "sample-task",
            "title": "Sample task",
            "objective": "Exercise the public CLI.",
            "acceptance_criteria": ["The CLI validates the contract."],
            "context_files": ["docs/context.md"],
            "editable_files": ["docs/output.md"],
            "test_commands": [["python", "-c", "print('ok')"]],
        }
        task_path = root / "agent" / "tasks" / "sample.json"
        task_path.write_text(json.dumps(task), encoding="utf-8")
        proposal_path = root / "proposal.json"
        proposal_path.write_text(json.dumps({
            "changes": [{"path": "docs/output.md", "content": "hello"}]
        }), encoding="utf-8")
        return task_path, proposal_path

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "agent.cli", *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_validate_task_reports_safe_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_target(root)

            result = self.run_cli(
                "--target-root", str(root),
                "validate-task", "agent/tasks/sample.json",
            )

            self.assertEqual(0, result.returncode, result.stderr)
            summary = json.loads(result.stdout)
            self.assertTrue(summary["valid"])
            self.assertEqual("sample-task", summary["task_id"])
            self.assertEqual(1, summary["editable_files"])

    def test_validate_proposal_reports_only_allowed_changed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, proposal = self.build_target(root)

            result = self.run_cli(
                "--target-root", str(root),
                "validate-proposal", "agent/tasks/sample.json", str(proposal),
            )

            self.assertEqual(0, result.returncode, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(["docs/output.md"], summary["changed_files"])

    def test_validate_proposal_fails_for_out_of_scope_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, proposal = self.build_target(root)
            proposal.write_text(json.dumps({
                "changes": [{"path": "README.md", "content": "bad"}]
            }), encoding="utf-8")

            result = self.run_cli(
                "--target-root", str(root),
                "validate-proposal", "agent/tasks/sample.json", str(proposal),
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("path not allowed", result.stderr)


if __name__ == "__main__":
    unittest.main()
