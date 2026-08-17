from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_c1_review_bundle.py"
SPEC = importlib.util.spec_from_file_location("export_c1_review_bundle", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReviewBundleSafetyTests(unittest.TestCase):
    def test_agent_environment_excludes_hosted_api_credentials(self) -> None:
        original = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "must-not-propagate"
        try:
            env = MODULE._agent_environment({"input": {"file_path": "public.csv"}}, "task")
        finally:
            if original is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertEqual(env["C1_TASK_ID"], "task")

    def test_public_artifact_accepts_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            path.write_text(
                json.dumps({"entrypoint": "agents/c1_baseline.py"}),
                encoding="utf-8",
            )
            MODULE._assert_public(path)

    def test_public_artifact_rejects_ground_truth_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            path.write_text('{"ground_truth_file": "hidden.csv"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE._assert_public(path)

    def test_public_artifact_rejects_windows_user_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            path.write_text('{"path": "C:\\\\Users\\\\name\\\\file"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE._assert_public(path)

    def test_json_writer_rejects_non_finite_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            with self.assertRaises(ValueError):
                MODULE._write_json(path, {"value": float("nan")})


if __name__ == "__main__":
    unittest.main()
