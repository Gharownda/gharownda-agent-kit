from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "agent" / "runtime" / "contracts.py"
spec = importlib.util.spec_from_file_location("contracts", MODULE_PATH)
contracts = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(contracts)


class ContractTest(unittest.TestCase):
    def test_extract_json_object(self):
        self.assertEqual(contracts.extract_json_object('prefix {"ok": true} suffix'), {"ok": True})

    def test_proposal_rejects_unlisted_path(self):
        task = {"editable_files": ["docs/TASKS.md"]}
        with self.assertRaises(ValueError):
            contracts.validate_proposal(task, {"changes": [{"path": "README.md", "content": "x"}]})

    def test_proposal_accepts_allowed_text_replacement(self):
        task = {"editable_files": ["docs/TASKS.md"]}
        changes = contracts.validate_proposal(task, {"changes": [{"path": "docs/TASKS.md", "content": "hello"}]})
        self.assertEqual(changes[0]["path"], "docs/TASKS.md")


    def test_external_target_root_is_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "agent" / "tasks").mkdir(parents=True)
            (root / "docs").mkdir()
            (root / "docs" / "context.md").write_text("context", encoding="utf-8")
            task = {
                "id": "external-target",
                "title": "External target",
                "objective": "Prove external target support.",
                "acceptance_criteria": ["Loads from target root."],
                "context_files": ["docs/context.md"],
                "editable_files": ["docs/output.md"],
                "test_commands": [["python", "-c", "print('ok')"]],
            }
            (root / "agent" / "tasks" / "external.json").write_text(json.dumps(task), encoding="utf-8")
            code = (
                "import sys;"
                f"sys.path.insert(0, {str(MODULE_PATH.parent)!r});"
                "import contracts;"
                "print(contracts.load_task('agent/tasks/external.json')[1]['id'])"
            )
            env = os.environ.copy()
            env["AGENT_TARGET_ROOT"] = str(root)
            completed = subprocess.run(
                [sys.executable, "-c", code],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("external-target", completed.stdout.strip())


if __name__ == "__main__":
    unittest.main()
