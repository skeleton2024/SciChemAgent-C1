"""Audit supplied C4 training labels without reading scorer ground truth."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any

import pandas as pd
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold


DEFAULT_HERG_TRAINING = Path(
    "benchmark/SciAgentArena/evaluations/dd/tasks_batch/data/herg_training_data.csv"
)


def _scaffold_key(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid hERG training SMILES: {smiles!r}")
    scaffold = MurckoScaffold.GetScaffoldForMol(mol)
    key = Chem.MolToSmiles(scaffold, canonical=True)
    if not key:
        raise ValueError(f"Empty Murcko scaffold for hERG training SMILES: {smiles!r}")
    return key


def summarize_herg_training(path: Path) -> dict[str, Any]:
    data = pd.read_csv(path)
    required = {"smiles", "activity"}
    missing = sorted(required.difference(data.columns))
    if missing:
        raise ValueError(f"Missing hERG training columns: {missing}")

    numeric_labels = pd.to_numeric(data["activity"], errors="coerce")
    if numeric_labels.isna().any() or not numeric_labels.isin([0, 1]).all():
        raise ValueError("hERG activity labels must be binary integers")
    labels = numeric_labels.astype(int).tolist()
    scaffolds = [_scaffold_key(str(smiles)) for smiles in data["smiles"]]

    scaffold_counts = Counter(scaffolds)
    scaffold_labels: dict[str, set[int]] = defaultdict(set)
    for scaffold, label in zip(scaffolds, labels):
        scaffold_labels[scaffold].add(label)

    class_counts = Counter(labels)
    return {
        "rows": len(data),
        "class_counts": {str(label): class_counts[label] for label in sorted(class_counts)},
        "positive_fraction": class_counts[1] / len(data) if len(data) else 0.0,
        "unique_murcko_scaffolds": len(scaffold_counts),
        "singleton_scaffolds": sum(count == 1 for count in scaffold_counts.values()),
        "largest_scaffold_group": max(scaffold_counts.values(), default=0),
        "scaffolds_with_both_labels": sum(
            len(scaffold_labels[scaffold]) == 2 for scaffold in scaffold_counts
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--herg-training", type=Path, default=DEFAULT_HERG_TRAINING)
    args = parser.parse_args()
    print(json.dumps(summarize_herg_training(args.herg_training), indent=2))


if __name__ == "__main__":
    main()
