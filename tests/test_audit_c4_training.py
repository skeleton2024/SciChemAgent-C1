from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.audit_c4_training import summarize_herg_training


class HergTrainingAuditTests(unittest.TestCase):
    def test_summary_is_invariant_to_row_order(self) -> None:
        rows = [
            {"smiles": "c1ccccc1O", "activity": 0},
            {"smiles": "Oc1ccccc1", "activity": 1},
            {"smiles": "c1ccncc1", "activity": 1},
        ]
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.csv"
            reversed_path = Path(directory) / "reversed.csv"
            pd.DataFrame(rows).to_csv(first, index=False)
            pd.DataFrame(list(reversed(rows))).to_csv(reversed_path, index=False)

            first_summary = summarize_herg_training(first)
            reversed_summary = summarize_herg_training(reversed_path)

        self.assertEqual(first_summary, reversed_summary)
        self.assertEqual(first_summary["unique_murcko_scaffolds"], 2)
        self.assertEqual(first_summary["scaffolds_with_both_labels"], 1)

    def test_nonbinary_labels_are_rejected_before_integer_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.csv"
            pd.DataFrame([{"smiles": "c1ccccc1", "activity": 0.5}]).to_csv(
                path,
                index=False,
            )

            with self.assertRaisesRegex(ValueError, "binary integers"):
                summarize_herg_training(path)


if __name__ == "__main__":
    unittest.main()
