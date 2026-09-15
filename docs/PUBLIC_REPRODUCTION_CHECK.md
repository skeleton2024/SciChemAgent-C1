# Public reproduction check

The public checkout's 18 regression tests passed during portfolio preparation on 2026-09-15, using an existing Python environment with RDKit and scikit-learn.

```text
python -m unittest discover -s tests -v
```

Coverage includes hERG label validation, molecular atom-map invariants, interpreter selection, and privacy constraints for the public review bundle. The C1/C4 benchmark scores in README remain the results of their original pinned runs; this check did not rerun those benchmarks.
