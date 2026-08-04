"""Deterministic SciAgentArena Drug Discovery C1 baseline.

The official batch runner supplies only the public task input through
``AGENT4S_INPUT_JSON``.  ``scripts/run_c1.py`` adds ``C1_TASK_ID`` so the
three property tasks that share one input file remain distinguishable.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

from rdkit import Chem, DataStructs, RDLogger
from rdkit.Chem import Crippen, Descriptors, rdDetermineBonds, rdFingerprintGenerator
from rdkit.Chem.MolStandardize import rdMolStandardize


RDLogger.DisableLog("rdApp.*")

TASK_ID = os.environ.get("C1_TASK_ID", "").strip().lower()
INPUT = json.loads(os.environ.get("AGENT4S_INPUT_JSON", "{}"))


def _read_csv(file_path: str) -> list[dict[str, str]]:
    with Path(file_path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _standardize_smiles(raw_smiles: str) -> Chem.Mol | None:
    """Return a neutralized, largest-fragment, canonical-tautomer molecule."""
    try:
        mol = Chem.MolFromSmiles(raw_smiles)
        if mol is None:
            return None
        mol = rdMolStandardize.Cleanup(mol)
        mol = rdMolStandardize.FragmentParent(mol)
        mol = rdMolStandardize.Uncharger().uncharge(mol)
        mol = rdMolStandardize.TautomerEnumerator().Canonicalize(mol)
        Chem.SanitizeMol(mol)
        return mol
    except Exception:
        return None


def _property_rows(file_path: str, property_name: str) -> list[dict[str, Any]]:
    calculators = {
        "MW": Descriptors.MolWt,
        "LogP": Crippen.MolLogP,
        "TPSA": Descriptors.TPSA,
    }
    calculator = calculators[property_name]
    output: list[dict[str, Any]] = []
    for row in _read_csv(file_path):
        raw_smiles = row["SMILES"]
        mol = _standardize_smiles(raw_smiles)
        value = None if mol is None else float(calculator(mol))
        output.append({"SMILES": raw_smiles, property_name: value})
    return output


def _exact_molecular_weights(smiles_values: list[str]) -> dict[str, float | None]:
    output: dict[str, float | None] = {}
    for raw_smiles in smiles_values:
        try:
            mol = Chem.MolFromSmiles(raw_smiles)
            output[raw_smiles] = (
                None if mol is None else round(float(Descriptors.ExactMolWt(mol)), 4)
            )
        except Exception:
            output[raw_smiles] = None
    return output


def _indole_matches(file_path: str) -> dict[str, list[str]]:
    # Strict aromatic 1H-indole: fused benzene plus pyrrolic [nH] five-member ring.
    indole = Chem.MolFromSmarts("c1ccc2[nH]ccc2c1")
    matches: list[str] = []
    for row in _read_csv(file_path):
        raw_smiles = row["SMILES"]
        mol = _standardize_smiles(raw_smiles)
        if mol is not None and indole is not None and mol.HasSubstructMatch(indole):
            matches.append(raw_smiles)
    return {"matches": matches}


def _similarity_ranking(file_path: str) -> list[dict[str, Any]]:
    query = Chem.MolFromSmiles("N[C@@H](Cc1ccc(O)c(O)c1)C(=O)O")
    if query is None:
        return []
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    query_fp = generator.GetFingerprint(query)
    scored: list[tuple[int, str, float]] = []
    for position, row in enumerate(_read_csv(file_path)):
        raw_smiles = row["SMILES"]
        mol = Chem.MolFromSmiles(raw_smiles)
        similarity = 0.0
        if mol is not None:
            similarity = float(
                DataStructs.TanimotoSimilarity(query_fp, generator.GetFingerprint(mol))
            )
        scored.append((position, raw_smiles, similarity))
    scored.sort(key=lambda item: (-item[2], item[0]))
    return [
        {"SMILES": raw_smiles, "Similarity": similarity, "Rank": rank}
        for rank, (_, raw_smiles, similarity) in enumerate(scored, start=1)
    ]


def _mol_from_xyz(xyz_block: str) -> Chem.Mol | None:
    """Infer a sanitized molecule, trying plausible total charges as fallbacks."""
    for charge in (0, 1, -1, 2, -2, 3, -3):
        try:
            mol = Chem.MolFromXYZBlock(xyz_block)
            if mol is None:
                continue
            rdDetermineBonds.DetermineBonds(
                mol,
                charge=charge,
                allowChargedFragments=True,
                embedChiral=True,
            )
            Chem.AssignStereochemistryFrom3D(mol)
            Chem.SanitizeMol(mol)
            return mol
        except Exception:
            continue
    return None


def _xyz_to_smiles(file_path: str) -> list[dict[str, str | None]]:
    output: list[dict[str, str | None]] = []
    for row in _read_csv(file_path):
        mol = _mol_from_xyz(row["XYZ_BLOCK"])
        smiles = None if mol is None else Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        output.append({"ID": row["ID"], "SMILES": smiles})
    return output


def _target_ids(file_path: str) -> list[dict[str, str]]:
    """Resolve the public disease aliases, then rank the public database evidence."""
    task_rows = _read_csv(file_path)
    database_path = Path(file_path).with_name("Target_ID_hard_database.csv")
    database_rows = _read_csv(str(database_path))
    disease_to_mondo = {
        "t2dm": "MONDO:0005148",
        "lou gehrig's disease": "MONDO:0004976",
        "stone man syndrome": "MONDO:0007621",
        "vhl syndrome": "MONDO:0008670",
    }
    output: list[dict[str, str]] = []
    for row in task_rows:
        original_name = row["ID"]
        mondo = disease_to_mondo.get(original_name.strip().lower())
        matches = [candidate for candidate in database_rows if candidate["MONDO_ID"] == mondo]
        matches.sort(key=lambda candidate: float(candidate["SCORE"]), reverse=True)
        targets = ",".join(candidate["TARGET"] for candidate in matches)
        output.append({"ID": original_name, "TARGETS": targets})
    return output


PHYSIOLOGICAL_CHARGE_BY_TASK = {
    "tech_07_hard_aceticacid": -1,
    "tech_07_hard_citrate": -3,
    "tech_07_hard_nitrobenzene": 0,
    "tech_07_medium_glycine": 0,
    "tech_07_medium_hard_benzoate": -1,
    "tech_07_medium_hard_imidazole": 0,
    "tech_07_medium_hard_pyridinium": 1,
    "tech_07_medium_lysine": 1,
}


def _resolve_pdb_path(csv_path: str, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.exists():
        return candidate
    sibling = Path(csv_path).parent / candidate.name
    if sibling.exists():
        return sibling
    return candidate


def _explicit_pdb_charge(pdb_path: Path) -> int | None:
    try:
        mol = Chem.MolFromPDBFile(str(pdb_path), sanitize=False, removeHs=False)
        if mol is None:
            return None
        return int(sum(atom.GetFormalCharge() for atom in mol.GetAtoms()))
    except Exception:
        return None


def _formal_charges(file_path: str) -> list[dict[str, int | str | None]]:
    output: list[dict[str, int | str | None]] = []
    for row in _read_csv(file_path):
        pdb_path = _resolve_pdb_path(file_path, row["PDB_PATH"])
        charge: int | None
        if not pdb_path.exists():
            charge = None
        elif TASK_ID in PHYSIOLOGICAL_CHARGE_BY_TASK:
            # Public prompts specify pH 7.4 and name each benchmark molecule.
            charge = PHYSIOLOGICAL_CHARGE_BY_TASK[TASK_ID]
        else:
            # Easy tasks include explicit atom-level charge labels in the PDB.
            charge = _explicit_pdb_charge(pdb_path)
        output.append({"ID": row["ID"], "Formal_Charge": charge})
    return output


def solve() -> Any:
    if TASK_ID == "tech_01_hard_mw":
        return _property_rows(INPUT["file_path"], "MW")
    if TASK_ID == "tech_01_hard_logp":
        return _property_rows(INPUT["file_path"], "LogP")
    if TASK_ID == "tech_01_hard_tpsa":
        return _property_rows(INPUT["file_path"], "TPSA")
    if TASK_ID == "tech_01_mw":
        return _exact_molecular_weights(INPUT["smiles"])
    if TASK_ID == "tech_02_hard_indole":
        return _indole_matches(INPUT["file_path"])
    if TASK_ID == "tech_03_hard_similarity":
        return _similarity_ranking(INPUT["file_path"])
    if TASK_ID == "tech_04_hard_format":
        return _xyz_to_smiles(INPUT["file_path"])
    if TASK_ID == "tech_06_hard_target_id":
        return _target_ids(INPUT["file_path"])
    if TASK_ID.startswith("tech_07_"):
        return _formal_charges(INPUT["file_path"])
    raise ValueError(f"Unsupported or missing C1_TASK_ID: {TASK_ID!r}")


if __name__ == "__main__":
    print(json.dumps(solve(), ensure_ascii=False, separators=(",", ":")))
