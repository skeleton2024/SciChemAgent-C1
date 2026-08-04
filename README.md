# SciChemAgent-C1

[中文说明](README.zh-CN.md)

SciChemAgent-C1 is a deterministic, offline baseline for the 18 Chemical Data
Preprocessing (C1) tasks in the
[SciAgentArena](https://sciagentarena.github.io/) drug-discovery benchmark. It
uses RDKit and public task inputs only; it does not call hosted LLMs, external
APIs, or network services at evaluation time.

This repository is a community submission candidate, not an official
leaderboard result until the SciAgentArena maintainers reproduce and accept it.

## Verified result

Evaluated on upstream commit
`c413f660304bf5def1c54a23619267e3ee2ef6ad` on 2026-08-04:

| Metric | Result |
|---|---:|
| Tasks accounted for | 18/18 |
| Mean executability | 1.0000 |
| Mean validity | 1.0000 |
| Mean correctness | 0.9244444444 (92.4444%) |
| Full-correctness tasks | 15/18 |

The correctness figure is the unweighted arithmetic mean over the 18 official
C1 task scores. `scripts/verify_results.py` independently checks the task-ID
set, metric bounds, per-task records, and the aggregate calculation.

The three non-perfect task scores were:

| Task | Correctness | Note |
|---|---:|---|
| `tech_03_hard_similarity` | 0.89 | Protonation-sensitive raw Morgan ranking |
| `tech_06_hard_target_id` | 0.75 | Returns all evidence-backed targets; scorer accepts only the top association |
| `tech_07_hard_aceticacid` | 0.00 | Benchmark ground truth conflicts with the stated pH 7.4 condition |

Full machine-readable aggregates are in
[`results/c1/summary.json`](results/c1/summary.json) and
[`results/c1/summary.csv`](results/c1/summary.csv).

## Method

- MW, LogP, and TPSA: RDKit cleanup, largest-fragment selection,
  neutralization, canonical tautomer selection, then descriptor calculation.
- Exact MW: `Descriptors.ExactMolWt`, rounded to four decimal places.
- Indole detection: strict aromatic 1H-indole SMARTS matching.
- Similarity: Morgan radius 2, 2048 bits, descending Tanimoto ranking.
- XYZ conversion: infer connectivity, bond orders, and stereochemistry from 3D
  coordinates with RDKit.
- Disease targets: resolve public aliases to MONDO IDs, then rank public
  database evidence.
- Formal charge: use explicit PDB charges or the dominant pH 7.4 microstate
  named by the public task.

The agent does not import SciAgentArena scorer modules or ground-truth files.

## Reproduce

The commands below target Windows PowerShell and Python 3.12:

```powershell
git clone --filter=blob:none https://github.com/HelloWorldLTY/SciAgentArena.git benchmark/SciAgentArena
git -C benchmark/SciAgentArena fetch --depth 1 origin c413f660304bf5def1c54a23619267e3ee2ef6ad
git -C benchmark/SciAgentArena checkout --detach c413f660304bf5def1c54a23619267e3ee2ef6ad

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-c1.txt

git -C benchmark/SciAgentArena apply --unidiff-zero ..\..\patches\sciagentarena-c1-mw-scorer.patch
.\.venv\Scripts\python.exe scripts\run_c1.py
.\.venv\Scripts\python.exe scripts\verify_results.py
```

The compatibility patch is necessary because the pinned upstream task index
references `oracle_chem.molecular_weight_score`, while that function is absent
from the pinned `oracle_chem.py`. The patch implements the public
`{SMILES: ExactMolWt}` contract with the documented 0.01 Da tolerance; it does
not modify agent predictions.

## Scientific-integrity note

`tech_07_hard_aceticacid` requests the dominant formal charge at pH 7.4. With
acetic-acid pKa approximately 4.76,

```text
[acetate]/[acetic acid] = 10^(7.40 - 4.76) ≈ 437
acetate fraction = 437 / (437 + 1) ≈ 99.77%
```

The dominant integer formal charge is therefore -1, but the pinned scorer uses
0. SciChemAgent-C1 keeps the chemically consistent -1 instead of hard-coding
the conflicting benchmark answer.

## Layout

- `agents/c1_baseline.py` — offline C1 agent
- `scripts/run_c1.py` — index-driven 18-task evaluator
- `scripts/verify_results.py` — independent result verification
- `patches/` — reproducible upstream compatibility patch
- `results/c1/` — aggregate results (raw logs and machine-specific records are
  intentionally excluded)

## License

MIT. See [LICENSE](LICENSE).
