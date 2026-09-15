from __future__ import annotations

import json
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from agent.private_target import select_work


class PrivateTargetSelectorTest(unittest.TestCase):
    def completed(self, stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")

    def test_task_marker_is_parsed_only_from_explicit_private_pr_marker(self):
        self.assertEqual(
            select_work.task_id_from_pr_body("Automated proposal\n\nTask: `V1-06` — Shopping"),
            "V1-06",
        )
        self.assertIsNone(select_work.task_id_from_pr_body("Please work on V1-06"))

    def test_trusted_change_request_requires_configured_reviewer(self):
        pr = {
            "reviews": [
                {"author": {"login": "untrusted"}, "state": "CHANGES_REQUESTED"},
                {"author": {"login": "maintainer"}, "state": "APPROVED"},
            ]
        }
        self.assertFalse(select_work.has_trusted_change_request(pr, {"maintainer"}))
        pr["reviews"].append({"author": {"login": "maintainer"}, "state": "CHANGES_REQUESTED"})
        self.assertTrue(select_work.has_trusted_change_request(pr, {"maintainer"}))

    def test_failed_checks_detect_only_terminal_failure_states(self):
        self.assertFalse(select_work.has_failed_checks({"statusCheckRollup": [{"conclusion": "SUCCESS"}]}))
        self.assertTrue(select_work.has_failed_checks({"statusCheckRollup": [{"conclusion": "FAILURE"}]}))

    def test_repair_attempts_are_derived_from_private_branch_commits(self):
        response = self.completed(json.dumps({"total_commits": 3}))
        with patch.object(select_work, "run", return_value=response) as mocked:
            attempts = select_work.repair_attempts(Path("."), "owner/private", "agent/task-name")

        self.assertEqual(attempts, 2)
        self.assertIn("agent%2Ftask-name", mocked.call_args.args[0][-1])
        self.assertEqual(select_work.MAX_REPAIR_ATTEMPTS, 2)

    def test_stale_managed_lease_is_reclaimed(self):
        stale = (datetime.now(timezone.utc) - select_work.LEASE_TTL - timedelta(minutes=1)).isoformat()
        refs = json.dumps([
            {"ref": "refs/heads/agent-lease/abc", "object": {"sha": "lease-sha"}}
        ])
        commit = json.dumps({
            "message": f"{select_work.LEASE_MESSAGE_PREFIX} abc",
            "committer": {"date": stale},
        })
        responses = [self.completed(refs), self.completed(commit), self.completed()]

        with patch.object(select_work, "run", side_effect=responses) as mocked:
            leases = select_work.active_leases(Path("."), "owner/private")

        self.assertEqual(leases, set())
        delete_args = mocked.call_args_list[-1].args[0]
        self.assertEqual(delete_args[:4], ["gh", "api", "--method", "DELETE"])
        self.assertTrue(delete_args[-1].endswith("agent-lease/abc"))

    def test_unknown_lease_is_never_reclaimed_automatically(self):
        old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        refs = json.dumps([
            {"ref": "refs/heads/agent-lease/abc", "object": {"sha": "other-sha"}}
        ])
        commit = json.dumps({"message": "ordinary commit", "committer": {"date": old}})

        with patch.object(select_work, "run", side_effect=[self.completed(refs), self.completed(commit)]):
            leases = select_work.active_leases(Path("."), "owner/private")

        self.assertEqual(leases, {"abc"})


if __name__ == "__main__":
    unittest.main()
