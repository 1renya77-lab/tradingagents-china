import unittest
from pathlib import Path

from tradingagents.utils.artifacts import resolve_artifact_dir, sanitize_run_name


class ArtifactsTest(unittest.TestCase):
    def test_resolve_default_artifact_dir(self):
        path = resolve_artifact_dir("/tmp/project", "reports")
        self.assertEqual(path, Path("/tmp/project").resolve() / "outputs" / "reports")

    def test_resolve_run_scoped_artifact_dir(self):
        path = resolve_artifact_dir("/tmp/project", "reports", run_name="with memory/测试")
        self.assertEqual(
            path,
            Path("/tmp/project").resolve() / "outputs" / "runs" / "with_memory" / "reports",
        )

    def test_sanitize_empty_run_name(self):
        self.assertEqual(sanitize_run_name("../"), "")


if __name__ == "__main__":
    unittest.main()
