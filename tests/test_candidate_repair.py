from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[1] / "agent" / "runtime"
sys.path.insert(0, str(RUNTIME))
model_stub = types.ModuleType("model")
model_stub.load_gguf = lambda *_args, **_kwargs: None
sys.modules.setdefault("model", model_stub)

from repair_candidate import load_evidence, merge_proposals


class CandidateRepairTest(unittest.TestCase):
    def task(self) -> dict:
        return {"editable_files": ["app/a.rb", "app/b.rb"]}

    def test_repair_preserves_unmodified_previous_changes(self):
        previous = {
            "summary": "initial",
            "changes": [
                {"path": "app/a.rb", "content": "A1"},
                {"path": "app/b.rb", "content": "B1"},
            ],
            "tests_expected": [],
            "risks": [],
        }
        repair = {
            "summary": "repair",
            "changes": [{"path": "app/b.rb", "content": "B2"}],
            "tests_expected": ["tests"],
            "risks": [],
        }

        merged = merge_proposals(self.task(), previous, repair)

        by_path = {change["path"]: change["content"] for change in merged["changes"]}
        self.assertEqual(by_path, {"app/a.rb": "A1", "app/b.rb": "B2"})
        self.assertEqual(merged["summary"], "repair")

    def test_repair_cannot_expand_editable_scope(self):
        previous = {
            "summary": "initial",
            "changes": [{"path": "app/a.rb", "content": "A1"}],
        }
        repair = {
            "summary": "bad",
            "changes": [{"path": "outside.rb", "content": "no"}],
        }

        with self.assertRaises(ValueError):
            merge_proposals(self.task(), previous, repair)

    def test_changes_required_review_can_be_repair_evidence(self):
        record = {
            "task_id": "task-1",
            "valid": True,
            "verdict": "changes_required",
            "review": {"blocking_findings": ["missing behavior"]},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            path.write_text(json.dumps(record))
            title, evidence = load_evidence("task-1", verification_path=None, review_path=str(path))

        self.assertEqual(title, "Independent reviewer findings")
        self.assertEqual(evidence["blocking_findings"], ["missing behavior"])


if __name__ == "__main__":
    unittest.main()
