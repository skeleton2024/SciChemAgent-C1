# SciChemAgent development plan

## Objective

Build a reproducible, scientifically defensible SciAgentArena agent whose
performance survives new molecules and upstream changes. Public benchmark
scores are regression signals, not the sole optimization target.

## Verified baseline

The current local C4 reproduction uses SciAgentArena commit `c413f660` and six
registered tasks. The full run regenerated on 2026-08-12 produced:

| Metric | Value | Source |
|---|---:|---|
| Tasks completed | 6/6 | `results/c4/summary.json` |
| Mean executability | 1.0000000000 | six task records |
| Mean validity | 1.0000000000 | six task records |
| Mean normalized correctness | 0.8997703514 | arithmetic mean after per-task normalization |
| Mean normalized strategic success | 0.3035333333 | arithmetic mean; four scorers leave this field at zero |

The correctness mean is the useful cross-task regression metric. Strategic
success is retained for completeness but is not a comparable six-task KPI.
These are local community-reproduced values, not official leaderboard scores.

## Risks to address

1. **Generalization:** the metabolic-soft-spot implementation contains a
   ten-CID reference table. It is transparent and reproducible, but the perfect
   public-task score does not establish performance on unseen molecules.
2. **Benchmark coupling:** the toxicophore vocabulary is aligned with open
   benchmark alert definitions. Atom-index aggregation also follows the pinned
   scorer's observed contract; a chemically reasonable per-match experiment
   reduced its F1 from 0.6871 to 0.3690 and was therefore reverted.
3. **Upstream drift:** the reproducible result is pinned to `c413f660`, while
   upstream has moved on and independently repaired the missing C1 molecular-
   weight scorer. The old C1 patch is historical compatibility material.
4. **Test depth:** the full evaluator is strong end-to-end evidence, but fast
   unit and metamorphic tests are still sparse.
5. **Metric semantics:** C4 scorers use mixed raw scales and do not uniformly
   implement strategic success. Any report must preserve per-task definitions.

## Roadmap

### Phase 0 — Harden the reproducible baseline (completed locally)

- Fail immediately on invalid checked-in SMARTS instead of silently dropping a
  rule.
- Discover `.venv` Python on Windows and POSIX, with the running interpreter as
  a final fallback.
- Reject evaluator records whose returned task ID does not match the requested
  task.
- Independently compile all 104 SMARTS in the result verifier.
- Avoid evaluating the metabolic fallback for known reference records and
  cover that behavior with a unit test.

Gate: unit test, syntax compilation, dependency check, six-task run, C1 and C4
independent verifiers, hygiene scan, and `git diff --check` all pass.

### Phase 1 — Prepare a reviewable C4 change set (completed locally)

- Review every intended file and remove generated or machine-specific material.
- Document pinned-versus-current-upstream reproduction paths. Do not propose
  the historical C1 patch as a new upstream fix.
- Add the compact test command to both READMEs and cover Linux path handling
  without changing the pinned score.
- Produce a file-by-file submission manifest and a concise PR description.

Gate: only intentional paths remain; all Phase 0 checks pass in the pinned
environment; no credential or absolute-user-path scan hits. A true fresh
dependency installation remains a separately labelled follow-up because the
local package cache was empty and network installation was not authorized.

Authorization: local preparation is allowed. Commit, push, or PR interaction
requires explicit user approval.

### Phase 2 — Build a generalization test harness

- Add chemistry metamorphic tests: atom renumbering, equivalent SMILES,
  duplicated motifs, invalid rows, and stable output ordering.
- Treat atom-map integrity and renumbering tests as input-contract evidence;
  they do not establish biological accuracy on unseen molecules.
- For learned hERG and PAINS-v1 tasks, report deterministic scaffold-split or
  grouped cross-validation metrics using only the supplied training labels.
- Define an internal OOD scorecard per task; never use scorer ground-truth files
  as runtime features or tuning inputs.
- Keep the pinned six-task evaluation as a non-regression check, not the model-
  selection objective.

Gate: deterministic reruns; no leakage across scaffold groups; malformed inputs
fail clearly; pinned executability and validity remain 1.0.

### Phase 3 — Replace the metabolic CID table with a general model

- Enumerate candidate mapped atoms and reaction classes from structure.
- Rank candidates with auditable descriptors: local environment, heteroatom
  adjacency, aromatic accessibility, benzylic or allylic activation, and steric
  exposure.
- Predict enzyme families with explicit rules or a model trained only on a
  separately documented public dataset.
- Retain the CID table only as a labelled reproduction profile until the
  general implementation meets an agreed validation gate.

Gate: report unseen or scaffold-held-out top-1 atom accuracy and enzyme-family
accuracy with confidence intervals or bootstrap ranges; publish failures, not
only the mean. The public ten-molecule result must be reported separately.

### Phase 4 — Decouple toxicophore chemistry from scorer compatibility

- Represent every SMARTS match separately in an internal typed structure.
- Add a compatibility serializer for the pinned scorer's index aggregation
  behavior instead of mixing that behavior into chemistry logic.
- Normalize alert names and document provenance for every rule.
- Test overlapping and repeated alerts on hand-constructed molecules.

Gate: chemistry-level tests pass, the compatibility serializer reproduces the
pinned 0.6871 F1, and alternative serialization is reported as an explicit
experiment rather than silently replacing the baseline.

### Phase 5 — Upstream and category expansion

- Submit the C4 package only after the reviewable manifest is approved.
- Respond to maintainer feedback with focused patches and rerun relevant gates.
- Consider another SciAgentArena category only after the C4 generalization
  harness and documentation are complete.

Authorization: commit, push, PR creation or commenting, merge, and deployment
all require explicit user approval.

## Recommended next development slice

Review the Phase 1 manifest and draft first. After explicit commit/push
authorization, publish the bounded C4 package. Then start Phase 2 before
attempting another public-score improvement.
