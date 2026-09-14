import json
import re
import unittest
from pathlib import Path


class DocumentationExamplesTest(unittest.TestCase):
    def test_json_code_blocks_are_valid(self):
        failures = []

        for path in sorted(Path(".").rglob("*.md")):
            if ".git" in path.parts:
                continue

            text = path.read_text(encoding="utf-8")
            for index, match in enumerate(
                re.finditer(r"```json\s*\n(.*?)\n```", text, flags=re.DOTALL),
                start=1,
            ):
                try:
                    json.loads(match.group(1))
                except json.JSONDecodeError as error:
                    failures.append(
                        f"{path} JSON block {index}: "
                        f"{error.msg} at line {error.lineno}, column {error.colno}"
                    )

        self.assertEqual([], failures, "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
