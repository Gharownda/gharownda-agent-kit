from __future__ import annotations

import json
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from agent.private_target import select_work


class PrivateTargetSelectorTest(unittest.TestCase):
    def completed(
        self,
        stdout: str = "",
        returncode: int = 0,
        stderr: str = "",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)

    def test_task_marker_is_parsed_only_from_explicit_private_pr_marker(self):
        self.assertEqual(
            select_work.task_id_from_pr_body("Automated proposal\n\nTask: `V1-06` — Shopping"),
            "V1-06",
        )
        self.assertIsNone(select_work.task_id_from_pr_body("Please work on V1-06"))

    def test_trusted_change_request_requires_configured_reviewer(self):
        pr = {
            "reviews": [
                {"id": 1, "author": {"login": "untrusted"}, "state": "CHANGES_REQUESTED"},
                {"id": 2, "author": {"login": "maintainer"}, "state": "APPROVED"},
            ]
        }
        self.assertFalse(select_work.has_trusted_change_request(pr, {"maintainer"}))
        pr["reviews"].append(
            {"id": 3, "author": {"login": "maintainer"}, "state": "CHANGES_REQUESTED"}
        )
        self.assertTrue(select_work.has_trusted_change_request(pr, {"maintainer"}))

    def test_newer_trusted_approval_clears_older_change_request(self):
        pr = {
            "reviews": [
                {"id": 10, "author": {"login": "maintainer"}, "state": "CHANGES_REQUESTED"},
                {"id": 11, "author": {"login": "maintainer"}, "state": "APPROVED"},
            ]
        }
        self.assertFalse(select_work.has_trusted_change_request(pr, {"maintainer"}))

    def test_open_prs_use_rest_api_and_normalize_head(self):
        payload = json.dumps(
            [
                {
                    "number": 42,
                    "body": "Task: `V1-06`",
                    "head": {"ref": "agent/v1-06", "sha": "abc"},
                }
            ]
        )
        with patch.object(select_work, "run", return_value=self.completed(payload)) as mocked:
            prs = select_work.list_open_prs(Path("."), "owner/private")

        self.assertEqual(
            prs,
            [{"number": 42, "headRefName": "agent/v1-06", "body": "Task: `V1-06`"}],
        )
        command = mocked.call_args.args[0]
        self.assertEqual(command[:3], ["gh", "api", "-H"])
        self.assertIn("repos/owner/private/pulls?state=open&per_page=100", command)

    def test_open_pr_permission_failure_is_actionable(self):
        with patch.object(select_work, "run", return_value=self.completed(returncode=1)):
            with self.assertRaisesRegex(RuntimeError, "Pull requests: read/write"):
                select_work.list_open_prs(Path("."), "owner/private")

    def test_failed_target_runs_consider_only_latest_run_per_workflow(self):
        payload = json.dumps(
            {
                "workflow_runs": [
                    {
                        "workflow_id": 1,
                        "run_number": 8,
                        "status": "completed",
                        "conclusion": "success",
                    },
                    {
                        "workflow_id": 1,
                        "run_number": 7,
                        "status": "completed",
                        "conclusion": "failure",
                    },
                    {
                        "workflow_id": 2,
                        "run_number": 5,
                        "status": "completed",
                        "conclusion": "success",
                    },
                ]
            }
        )
        with patch.object(select_work, "run", return_value=self.completed(payload)) as mocked:
            self.assertFalse(
                select_work.has_failed_target_runs(Path("."), "owner/private", "agent/v1-06")
            )

        command = mocked.call_args.args[0]
        self.assertEqual(command[:3], ["gh", "api", "-H"])
        self.assertIn("branch=agent%2Fv1-06", command[-1])

    def test_latest_failed_target_run_requests_repair(self):
        payload = json.dumps(
            {
                "workflow_runs": [
                    {
                        "workflow_id": 1,
                        "run_number": 9,
                        "status": "completed",
                        "conclusion": "failure",
                    },
                    {
                        "workflow_id": 1,
                        "run_number": 8,
                        "status": "completed",
                        "conclusion": "success",
                    },
                ]
            }
        )
        with patch.object(select_work, "run", return_value=self.completed(payload)):
            self.assertTrue(
                select_work.has_failed_target_runs(Path("."), "owner/private", "agent/v1-06")
            )

    def test_running_newer_target_run_suppresses_older_failure(self):
        payload = json.dumps(
            {
                "workflow_runs": [
                    {
                        "workflow_id": 1,
                        "run_number": 10,
                        "status": "in_progress",
                        "conclusion": None,
                    },
                    {
                        "workflow_id": 1,
                        "run_number": 9,
                        "status": "completed",
                        "conclusion": "failure",
                    },
                ]
            }
        )
        with patch.object(select_work, "run", return_value=self.completed(payload)):
            self.assertFalse(
                select_work.has_failed_target_runs(Path("."), "owner/private", "agent/v1-06")
            )

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
