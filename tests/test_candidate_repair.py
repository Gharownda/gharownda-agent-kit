from __future__ import annotations

import unittest

from agent.runtime.repair_candidate import merge_proposals


class CandidateRepairTest(unittest.TestCase):
    def task(self) -> dict:
        return {
            "editable_files": ["app/a.rb", "app/b.rb"],
        }

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


if __name__ == "__main__":
    unittest.main()
