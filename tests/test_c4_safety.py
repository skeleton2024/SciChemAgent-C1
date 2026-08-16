from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents import c4_safety
from scripts import run_c4


class MetabolicSoftSpotTests(unittest.TestCase):
    def test_known_reference_does_not_evaluate_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "query.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["ID", "Molecule", "Atom-mapped SMILES"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "ID": "5360696",
                        "Molecule": "reference",
                        "Atom-mapped SMILES": "invalid-on-purpose",
                    }
                )

            with mock.patch.object(
                c4_safety,
                "_fallback_soft_spot",
                side_effect=AssertionError("fallback should be lazy"),
            ):
                [result] = c4_safety._metabolic_soft_spots(str(path))

        self.assertEqual(result["atom_or_group"], "1")
        self.assertEqual(result["metabolic_enzyme"], "CYP2D6")

    def test_unseen_reference_rejects_empty_or_invalid_smiles(self) -> None:
        for mapped_smiles in ("", "not-a-smiles"):
            with self.subTest(mapped_smiles=mapped_smiles):
                with self.assertRaisesRegex(
                    ValueError,
                    "valid, non-empty molecule",
                ):
                    c4_safety._fallback_soft_spot(mapped_smiles)

    def test_unseen_reference_requires_positive_unique_atom_maps(self) -> None:
        cases = {
            "CO": "map every atom",
            "[CH3:0][OH:1]": "map every atom",
            "[CH3:1][OH:1]": "unique map number",
        }
        for mapped_smiles, message in cases.items():
            with self.subTest(mapped_smiles=mapped_smiles):
                with self.assertRaisesRegex(ValueError, message):
                    c4_safety._fallback_soft_spot(mapped_smiles)

    def test_unseen_reference_tracks_atom_map_renumbering(self) -> None:
        original = c4_safety._fallback_soft_spot(
            "[CH3:1][O:2][CH2:3][CH3:4]"
        )
        renumbered = c4_safety._fallback_soft_spot(
            "[CH3:11][O:12][CH2:13][CH3:14]"
        )

        self.assertEqual(original[0], 1)
        self.assertEqual(renumbered[0], 11)
        self.assertEqual(original[1:], renumbered[1:])


class PythonSelectionTests(unittest.TestCase):
    def test_windows_virtual_environment_takes_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            windows_python = workspace / ".venv" / "Scripts" / "python.exe"
            posix_python = workspace / ".venv" / "bin" / "python"
            windows_python.parent.mkdir(parents=True)
            posix_python.parent.mkdir(parents=True)
            windows_python.touch()
            posix_python.touch()

            selected = run_c4._select_python(workspace, Path("fallback-python"))

        self.assertEqual(selected, windows_python)

    def test_posix_virtual_environment_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            posix_python = workspace / ".venv" / "bin" / "python"
            posix_python.parent.mkdir(parents=True)
            posix_python.touch()

            selected = run_c4._select_python(workspace, Path("fallback-python"))

        self.assertEqual(selected, posix_python)

    def test_running_interpreter_is_the_final_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fallback = Path(directory) / "python"
            selected = run_c4._select_python(Path(directory), fallback)

        self.assertEqual(selected, fallback)


class SummaryProjectionTests(unittest.TestCase):
    def test_machine_specific_fields_are_not_published(self) -> None:
        raw = {
            "task_id": "reg_01_toxicophore",
            "executability": 1.0,
            "validity": 1.0,
            "correctness": 0.5,
            "strategic_success": 0.0,
            "details": {"machine_specific": True},
            "wall_time_seconds": 12.345,
        }

        summary = run_c4._summary_row(raw, 1.0)

        self.assertNotIn("details", summary)
        self.assertNotIn("wall_time_seconds", summary)
        self.assertEqual(summary["correctness_normalized"], 0.5)


if __name__ == "__main__":
    unittest.main()
