from __future__ import annotations

import importlib.util
import json
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


if __name__ == "__main__":
    unittest.main()
