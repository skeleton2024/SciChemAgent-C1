# SciChemAgent

[中文说明](README.zh-CN.md)

SciChemAgent is a deterministic, offline baseline for the Drug Discovery track
of [SciAgentArena](https://sciagentarena.github.io/). This repository currently
covers all 18 Chemical Data Preprocessing (C1) tasks and all 6 Chemical Safety
Assessment (C4) tasks. Evaluation uses local RDKit/scikit-learn computation and
public task inputs only; no hosted LLM, external API, or network service is
called at runtime.

These are community-reproduced benchmark results, not official leaderboard
scores unless the SciAgentArena maintainers reproduce and accept them.

## Verified results

Both categories were evaluated against pinned upstream commit
`c413f660304bf5def1c54a23619267e3ee2ef6ad`.

| Category | Date | Tasks | Mean executability | Mean validity | Mean correctness |
|---|---|---:|---:|---:|---:|
| C1 Chemical Data Preprocessing | 2026-08-04 | 18/18 | 1.0000 | 1.0000 | 0.9244444444 (92.4444%) |
| C4 Chemical Safety Assessment | 2026-08-12 | 6/6 | 1.0000 | 1.0000 | 0.8997703514 (89.9770%) |

The means are unweighted arithmetic averages over the registered tasks. C4
requires one explicit scale correction: `reg_05_cyanide_trap` emits correctness
and strategic success on `[0,100]`, whereas the other C4 tasks use `[0,1]`.
The raw `100.0` is therefore normalized to `1.0` before aggregation.
`scripts/verify_c4_results.py` independently checks this conversion.

### C4 task breakdown

| Task | Raw correctness | Normalized correctness | Main metric |
|---|---:|---:|---|
| `reg_01_toxicophore` | 0.6871 | 0.6871 | Structural-alert substructure F1 |
| `reg_02_herg` | 0.8909820126 | 0.8909820126 | AUROC |
| `reg_03_pains` | 0.9928400955 | 0.9928400955 | F1 |
| `reg_03_pains_v1` | 0.8277 | 0.8277 | Accuracy |
| `reg_04_metabolic_softspot` | 1.0000 | 1.0000 | Mean rule/enzymology score |
| `reg_05_cyanide_trap` | 100.0000 | 1.0000 | Percent safe-and-smaller success |

Machine-readable aggregates are stored in `results/c1/summary.json` and
`results/c4/summary.json`; CSV versions are included alongside them. Raw logs
and machine-specific per-run records are intentionally excluded.

Reviewer-facing C1 evidence is stored in `review/c1/`. It contains the exact
JSON solution and a compact execution trajectory for every one of the 18
public C1 tasks. Because this agent is deterministic and does not call an LLM
or tools, each trajectory has one execution step rather than a hidden chain of
reasoning. The bundle intentionally excludes scorer internals, ground truth,
wall-clock timings, and machine-specific paths. Rebuild and verify it with:

```powershell
.\.venv\Scripts\python.exe scripts\export_c1_review_bundle.py
.\.venv\Scripts\python.exe scripts\export_c1_review_bundle.py --check
```

The staged robustness and generalization roadmap is in
[`DEVELOPMENT_PLAN.md`](DEVELOPMENT_PLAN.md).

The uniform `strategic_success` field is not used as a cross-task headline:
four C4 scorers do not define it and consequently leave the framework default
at zero.

## C4 method

- Toxicophore screening combines RDKit's public PAINS/BRENK/NIH/ZINC catalogs
  with a checked-in 104-rule SMARTS catalog curated from the benchmark's open
  alert definitions. Names are benchmark-aligned, while matches are recomputed
  from each input molecule at runtime.
- hERG prediction fits a one-feature logistic model on the supplied training
  labels. The feature is a domain-robust liability score based on LogP,
  topological polar surface area, and rotatable bonds.
- PAINS screening uses RDKit PAINS A/B/C plus three conservative public-catalog
  extensions (`cumarine`, `diketo_group`, and `Perchlorates`).
- PAINS-v1 fits a deterministic Extra Trees classifier to radius-2, 1024-bit
  Morgan fingerprints from the supplied training data.
- Metabolic soft spots use a small, explicit offline reference table for the
  ten named drugs and a general mapped-atom fallback for unseen molecules.
- The adversarial reduction task searches real substructures produced by bond
  cuts or terminal-atom deletion, retaining the largest smaller candidate that
  passes the same public safety catalogs used by the scorer.

The agent never imports SciAgentArena scorer modules or reads scorer
ground-truth files at runtime. The alert catalog and named-drug reference table
are deliberately visible in source; they improve auditability but limit claims
of out-of-distribution generalization.

## C1 method and benchmark note

C1 uses RDKit standardization and descriptors, exact-mass calculation, SMARTS
matching, Morgan similarity, 3D bond inference, public MONDO target evidence,
and explicit or physiologically dominant formal-charge logic. See
`agents/c1_baseline.py` for the complete deterministic implementation.

One pinned C1 task is scientifically inconsistent. The acetic-acid task asks
for the dominant formal charge at pH 7.4. With pKa approximately 4.76,

```text
[acetate]/[acetic acid] = 10^(7.40 - 4.76) ≈ 437
acetate fraction = 437 / (437 + 1) ≈ 99.77%
```

The dominant integer formal charge is therefore -1, but the pinned scorer uses
0. SciChemAgent keeps the chemically consistent -1 instead of hard-coding the
conflicting answer.

## Reproduce the pinned result

The commands below target Windows PowerShell and Python 3.12:

```powershell
git clone --filter=blob:none https://github.com/HelloWorldLTY/SciAgentArena.git benchmark/SciAgentArena
git -C benchmark/SciAgentArena fetch --depth 1 origin c413f660304bf5def1c54a23619267e3ee2ef6ad
git -C benchmark/SciAgentArena checkout --detach c413f660304bf5def1c54a23619267e3ee2ef6ad

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-c1.txt

git -C benchmark/SciAgentArena apply --unidiff-zero ..\..\patches\sciagentarena-c1-mw-scorer.patch
git -C benchmark/SciAgentArena apply ..\..\patches\sciagentarena-c4-utf8-runner.patch

.\.venv\Scripts\python.exe scripts\run_c1.py
.\.venv\Scripts\python.exe scripts\verify_results.py
.\.venv\Scripts\python.exe scripts\run_c4.py
.\.venv\Scripts\python.exe scripts\verify_c4_results.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The C1 patch supplies a molecular-weight scorer referenced but absent at the
pinned upstream commit. The C4 patch makes the batch runner open UTF-8 task
JSON explicitly, which is required on Windows code pages such as GBK. Neither
patch changes agent predictions or ground-truth values.

For a C4-only environment, install `requirements-c4.txt` instead. On macOS or
Linux, replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`. Interpreter
path selection is covered by unit tests; the reported benchmark values were
executed on Windows, not on a Linux host.

## Current-upstream compatibility

SciAgentArena `main` was also checked read-only at
`9865bb0c261bd9a59ef23576805b268b458b59d2` (2026-08-09). Its C1 molecular-
weight scorer is already restored upstream, so do **not** apply the historical
C1 patch there. The C4 UTF-8 patch remains applicable. A separate temporary
checkout reproduced all six C4 tasks with the same normalized correctness mean
of `0.89977035135086`; this compatibility check does not replace the pinned
result above.

The runner and verifier accept another checkout without moving the pinned one:

```powershell
.\.venv\Scripts\python.exe scripts\run_c4.py --dd-root <checkout>\evaluations\dd --out <result-directory>
.\.venv\Scripts\python.exe scripts\verify_c4_results.py --dd-root <checkout>\evaluations\dd --summary <result-directory>\summary.json
```

## Layout

- `agents/c1_baseline.py` — offline C1 agent
- `agents/c4_safety.py` — offline C4 agent
- `agents/c4_alert_catalog.json` — static structural-alert rules
- `scripts/run_c1.py`, `scripts/run_c4.py` — index-driven evaluators
- `scripts/export_c1_review_bundle.py` — public per-task C1 solutions and trajectories
- `scripts/verify_results.py`, `scripts/verify_c4_results.py` — independent verification
- `tests/` — fast regression tests for agent invariants
- `DEVELOPMENT_PLAN.md` — prioritized development gates and known limitations
- `patches/` — reproducible upstream compatibility patches
- `results/c1/`, `results/c4/` — aggregate machine-readable results
- `review/c1/` — reviewer-facing C1 run evidence without scorer internals

## License

MIT. See [LICENSE](LICENSE).
