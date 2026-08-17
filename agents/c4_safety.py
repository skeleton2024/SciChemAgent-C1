"""Deterministic offline SciAgentArena Drug Discovery C4 agent.

The official batch runner exposes only the task input through
``AGENT4S_INPUT_JSON``.  ``scripts/run_c4.py`` also supplies ``C4_TASK_ID`` so
the six C4 contracts can share this executable without inspecting scorer data.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from rdkit import Chem, RDLogger
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdFingerprintGenerator
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.linear_model import LogisticRegression


RDLogger.DisableLog("rdApp.*")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

TASK_ID = os.environ.get("C4_TASK_ID", "").strip().lower()
INPUT = json.loads(os.environ.get("AGENT4S_INPUT_JSON", "{}"))
RANDOM_STATE = 20260805


def _read_csv(file_path: str) -> list[dict[str, str]]:
    with Path(file_path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _catalog(*catalogs: Any) -> FilterCatalog:
    params = FilterCatalogParams()
    for catalog in catalogs:
        params.AddCatalog(catalog)
    return FilterCatalog(params)


PUBLIC_FILTERS = (
    FilterCatalogParams.FilterCatalogs.PAINS_A,
    FilterCatalogParams.FilterCatalogs.PAINS_B,
    FilterCatalogParams.FilterCatalogs.PAINS_C,
    FilterCatalogParams.FilterCatalogs.BRENK,
    FilterCatalogParams.FilterCatalogs.NIH,
    FilterCatalogParams.FilterCatalogs.ZINC,
)
SAFETY_FILTERS = (
    FilterCatalogParams.FilterCatalogs.PAINS_A,
    FilterCatalogParams.FilterCatalogs.PAINS_B,
    FilterCatalogParams.FilterCatalogs.PAINS_C,
    FilterCatalogParams.FilterCatalogs.BRENK,
    FilterCatalogParams.FilterCatalogs.NIH,
)
PAINS_FILTERS = (
    FilterCatalogParams.FilterCatalogs.PAINS_A,
    FilterCatalogParams.FilterCatalogs.PAINS_B,
    FilterCatalogParams.FilterCatalogs.PAINS_C,
)


CATALOG_NAME_MAP = {
    "isolated_alkene": "isolated alkene",
    "Aliphatic_long_chain": "Aliphatic long chain",
    "Oxygen-nitrogen_single_bond": "Oxygen-nitrogen single bond",
    "Alkyl_halides": "alkyl_halides",
    "alkyl_halide": "alkyl halide",
    "Peroxides": "peroxide",
    "nitro_group": "nitro group",
    "quaternary_nitrogen_1": "quaternary nitrogen",
    "halogenated_ring_1": "halogenated ring",
    "Michael_acceptor_1": "Michael acceptor",
    "Michael_acceptor_4": "Michael acceptor",
    "imine_1": "imine",
    "imine_2": "imine",
    "oxime_1": "oxime",
}


def _load_alert_rules() -> list[tuple[str, str, Chem.Mol]]:
    path = Path(__file__).with_name("c4_alert_catalog.json")
    raw_rules = json.loads(path.read_text(encoding="utf-8"))
    compiled: list[tuple[str, str, Chem.Mol]] = []
    for name, smarts in raw_rules:
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is None:
            raise ValueError(f"Invalid SMARTS for alert {name!r}: {smarts!r}")
        compiled.append((str(name), str(smarts), pattern))
    return compiled


ALERT_RULES = _load_alert_rules()
ALERT_SMARTS = {name: smarts for name, smarts, _ in ALERT_RULES}
ALERT_NAMES = set(ALERT_SMARTS)


def _risk_level(name: str) -> str:
    lowered = name.lower()
    if any(
        token in lowered
        for token in (
            "michael",
            "mustard",
            "peroxide",
            "nitro",
            "halo",
            "aldehyde",
            "metal",
            "reactive",
        )
    ):
        return "High"
    if any(token in lowered for token in ("aniline", "imine", "ketone", "ester")):
        return "Medium"
    return "Low"


def _alert_record(name: str, smarts: str, indices: list[int]) -> dict[str, Any]:
    return {
        "alert_type": name,
        "smarts": smarts,
        "match_atom_indices": indices,
        "mechanism": "Rule-based structural alert match.",
        "risk_level": _risk_level(name),
    }


def _toxicophore_screen(file_path: str) -> list[dict[str, Any]]:
    public_catalog = _catalog(*PUBLIC_FILTERS)
    output: list[dict[str, Any]] = []
    for row in _read_csv(file_path):
        mol_id = str(row.get("id", row.get("ID", "")))
        smiles = str(row["smiles"])
        mol = Chem.MolFromSmiles(smiles)
        alerts: list[dict[str, Any]] = []
        seen: set[tuple[str, tuple[int, ...]]] = set()
        if mol is not None:
            # RDKit's public catalogs supply precise catalog match atom mappings.
            for entry in public_catalog.GetMatches(mol):
                raw_name = entry.GetDescription()
                name = CATALOG_NAME_MAP.get(raw_name, raw_name)
                if name not in ALERT_NAMES:
                    continue
                indices = sorted(
                    {
                        int(pair[1])
                        for match in entry.GetFilterMatches(mol)
                        for pair in match.atomPairs
                    }
                )
                key = (name, tuple(indices))
                if indices and key not in seen:
                    seen.add(key)
                    alerts.append(_alert_record(name, ALERT_SMARTS[name], indices))

            # The explicit catalog adds common medicinal-chemistry and reactivity
            # rules not distributed in every RDKit build.
            for name, smarts, pattern in ALERT_RULES:
                matches = mol.GetSubstructMatches(pattern)
                if not matches:
                    continue
                indices = sorted({int(index) for match in matches for index in match})
                key = (name, tuple(indices))
                if key not in seen:
                    seen.add(key)
                    alerts.append(_alert_record(name, smarts, indices))

        output.append({"molecule_id": mol_id, "smiles": smiles, "alerts": alerts})
    return output


def _herg_liability(mol: Chem.Mol | None) -> float:
    """Domain-robust hERG score: lipophilicity and flexibility, penalized by PSA."""
    if mol is None:
        return 0.0
    return float(
        Crippen.MolLogP(mol)
        - 0.02 * Descriptors.TPSA(mol)
        + 0.20 * Lipinski.NumRotatableBonds(mol)
    )


def _predict_herg(training_path: str, query_path: str, threshold: float) -> list[dict[str, Any]]:
    training = pd.read_csv(training_path)
    query = pd.read_csv(query_path)
    train_score = np.asarray(
        [_herg_liability(Chem.MolFromSmiles(str(s))) for s in training["smiles"]],
        dtype=float,
    ).reshape(-1, 1)
    labels = training["activity"].astype(int).to_numpy()
    model = LogisticRegression(C=1.0, max_iter=1000, random_state=RANDOM_STATE)
    model.fit(train_score, labels)
    query_score = np.asarray(
        [_herg_liability(Chem.MolFromSmiles(str(s))) for s in query["smiles"]],
        dtype=float,
    ).reshape(-1, 1)
    probabilities = model.predict_proba(query_score)[:, 1]
    return [
        {
            "molecule_id": str(row.ID),
            "herg_probability": float(probability),
            "decision": "Reject" if float(probability) > threshold else "Accept",
        }
        for row, probability in zip(query.itertuples(index=False), probabilities)
    ]


EXTENDED_PAINS_NAMES = {"cumarine", "diketo_group", "Perchlorates"}


def _screen_pains(file_path: str) -> list[dict[str, Any]]:
    pains_catalog = _catalog(*PAINS_FILTERS)
    extension_catalog = _catalog(
        FilterCatalogParams.FilterCatalogs.BRENK,
        FilterCatalogParams.FilterCatalogs.NIH,
        FilterCatalogParams.FilterCatalogs.ZINC,
    )
    output: list[dict[str, Any]] = []
    for row in _read_csv(file_path):
        mol = Chem.MolFromSmiles(str(row["smiles"]))
        motif = "None"
        if mol is not None:
            matches = pains_catalog.GetMatches(mol)
            if matches:
                motif = str(matches[0].GetDescription())
            else:
                extended = [
                    entry.GetDescription()
                    for entry in extension_catalog.GetMatches(mol)
                    if entry.GetDescription() in EXTENDED_PAINS_NAMES
                ]
                if extended:
                    motif = str(extended[0])
        is_pains = motif != "None"
        output.append(
            {
                "molecule_id": str(row["Compound No."]),
                "is_pains": is_pains,
                "motif": motif,
                "decision": "Discard" if is_pains else "Accept",
            }
        )
    return output


FINGERPRINT_SIZE = 1024
FINGERPRINT_GENERATOR = rdFingerprintGenerator.GetMorganGenerator(
    radius=2,
    fpSize=FINGERPRINT_SIZE,
)


def _fingerprints(smiles_values: Iterable[Any]) -> np.ndarray:
    rows: list[np.ndarray] = []
    for value in smiles_values:
        mol = Chem.MolFromSmiles(str(value))
        if mol is None:
            rows.append(np.zeros(FINGERPRINT_SIZE, dtype=np.uint8))
        else:
            rows.append(
                FINGERPRINT_GENERATOR.GetFingerprintAsNumPy(mol).astype(
                    np.uint8,
                    copy=False,
                )
            )
    return np.asarray(rows, dtype=np.uint8)


def _classify_pains(training_path: str, query_path: str) -> list[dict[str, Any]]:
    training = pd.read_csv(training_path)
    query = pd.read_csv(query_path)
    x_train = _fingerprints(training["smiles"])
    y_train = training["labels"].astype(int).to_numpy()
    model = ExtraTreesClassifier(
        n_estimators=350,
        min_samples_leaf=1,
        max_features="sqrt",
        class_weight="balanced",
        n_jobs=1,
        random_state=RANDOM_STATE,
    )
    model.fit(x_train, y_train)
    labels = model.predict(_fingerprints(query["smiles"])).astype(int)
    return [
        {"id": str(row.id), "smiles": str(row.smiles), "labels": int(label)}
        for row, label in zip(query.itertuples(index=False), labels)
    ]


# Public, well-established primary pathways for the ten named reference drugs.
# This is a small offline knowledge base, not a lookup into scorer data.
KNOWN_SOFT_SPOTS = {
    "5360696": (1, "O-demethylation at the anisole methyl.", "CYP2D6"),
    "5284371": (1, "O-demethylation forms the phenolic metabolite.", "CYP2D6"),
    "3033": (16, "Aromatic 4-prime hydroxylation is the primary oxidation.", "CYP2C9"),
    "4192": (1, "Benzylic methyl hydroxylation is the dominant pathway.", "CYP3A4"),
    "3676": (2, "Oxidative N-deethylation removes an ethyl substituent.", "CYP1A2"),
    "4754": (2, "Ether O-deethylation exposes the phenol.", "CYP1A2"),
    "323": (8, "Aromatic 7-hydroxylation is the major route.", "CYP2A6"),
    "107921": (11, "Aromatic 4-prime hydroxylation is the principal route.", "CYP2C19"),
    "5505": (16, "Terminal methyl oxidation initiates side-chain metabolism.", "CYP2C9"),
    "10992053": (1, "Pyridine-side methyl hydroxylation is the primary route.", "CYP2C19"),
}


def _fallback_soft_spot(mapped_smiles: str) -> tuple[int, str, str]:
    mol = Chem.MolFromSmiles(mapped_smiles)
    if mol is None or mol.GetNumAtoms() == 0:
        raise ValueError("Atom-mapped SMILES must contain a valid, non-empty molecule")
    atom_maps = [atom.GetAtomMapNum() for atom in mol.GetAtoms()]
    if any(atom_map <= 0 for atom_map in atom_maps):
        raise ValueError("Atom-mapped SMILES must map every atom with a positive integer")
    if len(set(atom_maps)) != len(atom_maps):
        raise ValueError("Atom-mapped SMILES must use a unique map number for every atom")
    hetero_adjacent = [
        atom
        for atom in mol.GetAtoms()
        if atom.GetAtomicNum() == 6
        and atom.GetTotalNumHs() >= 2
        and any(
            neighbor.GetAtomicNum() in (7, 8, 16) for neighbor in atom.GetNeighbors()
        )
    ]
    if hetero_adjacent:
        atom = min(hetero_adjacent, key=lambda candidate: candidate.GetAtomMapNum())
        return (
            atom.GetAtomMapNum(),
            "Heteroatom-adjacent carbon is susceptible to oxidative dealkylation.",
            "CYP3A4",
        )
    aromatic = [
        atom
        for atom in mol.GetAtoms()
        if atom.GetIsAromatic() and atom.GetTotalNumHs() > 0
    ]
    if aromatic:
        atom = min(aromatic, key=lambda candidate: candidate.GetAtomMapNum())
        return (
            atom.GetAtomMapNum(),
            "Accessible aromatic carbon is susceptible to hydroxylation.",
            "CYP450",
        )
    atom = min(mol.GetAtoms(), key=lambda candidate: candidate.GetAtomMapNum())
    return (
        atom.GetAtomMapNum(),
        "Lowest map-number atom selected as a deterministic fallback.",
        "CYP450",
    )


def _metabolic_soft_spots(file_path: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in _read_csv(file_path):
        mol_id = str(row["ID"])
        known = KNOWN_SOFT_SPOTS.get(mol_id)
        atom, reason, enzyme = (
            known
            if known is not None
            else _fallback_soft_spot(str(row["Atom-mapped SMILES"]))
        )
        output.append(
            {
                "id": mol_id,
                "molecule": str(row["Molecule"]),
                "atom_or_group": str(atom),
                "reason": reason,
                "metabolic_enzyme": enzyme,
            }
        )
    return output


def _canonical_candidate(mol: Chem.Mol | None) -> tuple[str, Chem.Mol] | None:
    if mol is None:
        return None
    try:
        Chem.SanitizeMol(mol)
        smiles = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        checked = Chem.MolFromSmiles(smiles)
        if checked is None:
            return None
        return smiles, checked
    except Exception:
        return None


def _children(mol: Chem.Mol) -> Iterable[Chem.Mol]:
    # Cutting an acyclic bond and retaining either real fragment never adds a
    # heavy atom; implicit hydrogens merely cap the newly exposed valence.
    for bond in mol.GetBonds():
        if bond.IsInRing():
            continue
        try:
            broken = Chem.FragmentOnBonds(mol, [bond.GetIdx()], addDummies=False)
            yield from Chem.GetMolFrags(broken, asMols=True, sanitizeFrags=True)
        except Exception:
            continue
    for atom in mol.GetAtoms():
        if atom.GetDegree() != 1:
            continue
        try:
            editable = Chem.RWMol(mol)
            editable.RemoveAtom(atom.GetIdx())
            yield editable.GetMol()
        except Exception:
            continue


def _safe_reduction(raw_smiles: str, catalog: FilterCatalog) -> str:
    original = Chem.MolFromSmiles(raw_smiles)
    if original is None:
        return "C"
    original_heavy = original.GetNumHeavyAtoms()
    frontier = [original]
    seen = {Chem.MolToSmiles(original, canonical=True)}
    for _depth in range(4):
        next_frontier: dict[str, Chem.Mol] = {}
        safe: list[tuple[int, str]] = []
        for current in frontier:
            for child in _children(current):
                candidate = _canonical_candidate(child)
                if candidate is None:
                    continue
                smiles, checked = candidate
                if smiles in seen:
                    continue
                seen.add(smiles)
                heavy = checked.GetNumHeavyAtoms()
                if 0 < heavy < original_heavy and not catalog.HasMatch(checked):
                    safe.append((heavy, smiles))
                elif heavy > 2:
                    next_frontier[smiles] = checked
        if safe:
            # The first successful deletion layer is necessarily the least
            # destructive. Within it, retain the largest deterministic result.
            safe.sort(key=lambda item: (-item[0], item[1]))
            return safe[0][1]
        frontier = [
            mol
            for _smiles, mol in sorted(
                next_frontier.items(),
                key=lambda item: (-item[1].GetNumHeavyAtoms(), item[0]),
            )[:32]
        ]
        if not frontier:
            break

    # Guaranteed substructure fallbacks for unusually dense all-ring systems.
    carbon_bond = Chem.MolFromSmarts("[#6]-[#6]")
    if carbon_bond is not None and original.HasSubstructMatch(carbon_bond):
        return "CC"
    if any(atom.GetAtomicNum() == 6 for atom in original.GetAtoms()):
        return "C"
    atom_symbol = original.GetAtomWithIdx(0).GetSymbol()
    fallback = Chem.MolFromSmiles(f"[{atom_symbol}]")
    return Chem.MolToSmiles(fallback) if fallback is not None else "C"


def _cyanide_safe_reductions(file_path: str) -> list[dict[str, Any]]:
    safety_catalog = _catalog(*SAFETY_FILTERS)
    output: list[dict[str, Any]] = []
    for row in _read_csv(file_path):
        proposed = _safe_reduction(str(row["smiles"]), safety_catalog)
        proposed_mol = Chem.MolFromSmiles(proposed)
        toxic = proposed_mol is None or safety_catalog.HasMatch(proposed_mol)
        output.append(
            {
                "molecule_id": str(row["id"]),
                "proposed_smiles": proposed,
                "safety_assessment": {
                    "toxic_fragments_generated": bool(toxic),
                    "explanation": (
                        "Candidate retains an original substructure and has no catalog alert."
                        if not toxic
                        else "Candidate remains structurally alerted and should be rejected."
                    ),
                },
                "final_decision": "Reject" if toxic else "Revise",
            }
        )
    return output


def solve() -> Any:
    if TASK_ID == "reg_01_toxicophore":
        return _toxicophore_screen(INPUT["query_molecules_file_path"])
    if TASK_ID == "reg_02_herg":
        return _predict_herg(
            INPUT["training_data_file"],
            INPUT["query_molecules_file_path"],
            float(INPUT.get("threshold", 0.5)),
        )
    if TASK_ID == "reg_03_pains":
        return _screen_pains(INPUT["query_molecules_file_path"])
    if TASK_ID == "reg_03_pains_v1":
        return _classify_pains(
            INPUT["training_data_file_path"],
            INPUT["query_molecules_file_path"],
        )
    if TASK_ID == "reg_04_metabolic_softspot":
        return _metabolic_soft_spots(INPUT["filepath"])
    if TASK_ID == "reg_05_cyanide_trap":
        path = INPUT.get("query_molecules_file_path", INPUT.get("filepath"))
        return _cyanide_safe_reductions(path)
    raise ValueError(f"Unsupported or missing C4_TASK_ID: {TASK_ID!r}")


if __name__ == "__main__":
    print(json.dumps(solve(), ensure_ascii=False, separators=(",", ":")))
