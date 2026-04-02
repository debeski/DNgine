from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class EntrypointTests(unittest.TestCase):
    def test_package_directory_entrypoint_works_from_source_tree(self) -> None:
        result = subprocess.run(
            [sys.executable, "dngine", "--help"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("usage: python -m dngine", result.stdout)


if __name__ == "__main__":
    unittest.main()
