import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1] / "agent" / "runtime"
sys.path.insert(0, str(RUNTIME))

import verify


class VerifierPathSafetyTest(unittest.TestCase):
    def test_accepts_regular_path_inside_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "src" / "candidate.py"
            target.parent.mkdir()

            with patch.object(verify, "REPO_ROOT", root):
                verify.ensure_safe_write_target(target)

    def test_rejects_symlink_file_even_when_target_is_inside_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real.txt"
            real.write_text("trusted")
            link = root / "candidate.txt"
            link.symlink_to(real)

            with patch.object(verify, "REPO_ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "must not be a symlink"):
                    verify.ensure_safe_write_target(link)

    def test_rejects_path_through_symlinked_parent_outside_repository(self):
        with tempfile.TemporaryDirectory() as repo_tmp, tempfile.TemporaryDirectory() as outside_tmp:
            root = Path(repo_tmp)
            linked_parent = root / "generated"
            linked_parent.symlink_to(Path(outside_tmp), target_is_directory=True)
            target = linked_parent / "candidate.txt"

            with patch.object(verify, "REPO_ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "resolves outside repository"):
                    verify.ensure_safe_write_target(target)


if __name__ == "__main__":
    unittest.main()
