from __future__ import annotations

import sys
import unittest
from pathlib import Path

PRIVATE_TARGET = Path(__file__).resolve().parents[1] / "agent" / "private_target"
sys.path.insert(0, str(PRIVATE_TARGET))

from report_failure import chunks, redact


class PrivateDiagnosticsTest(unittest.TestCase):
    def test_redacts_database_password_and_tokens(self):
        raw = (
            "postgresql://app:super-secret@db.example.test/app\n"
            "Authorization: Bearer github_pat_abc123\n"
            "token=ghp_deadbeef\n"
            "password=hunter2\n"
        )

        value = redact(raw)

        self.assertNotIn("super-secret", value)
        self.assertNotIn("github_pat_abc123", value)
        self.assertNotIn("ghp_deadbeef", value)
        self.assertNotIn("hunter2", value)
        self.assertIn("[REDACTED]", value)

    def test_chunks_preserve_complete_text(self):
        raw = "0123456789" * 23
        parts = chunks(raw, limit=37)

        self.assertEqual("".join(parts), raw)
        self.assertTrue(all(len(part) <= 37 for part in parts))
        self.assertGreater(len(parts), 1)


if __name__ == "__main__":
    unittest.main()
