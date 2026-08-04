"""Verify that the saved C1 result set is complete and numerically sane."""

from __future__ import annotations

import json
import math
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
INDEX = WORKSPACE / "benchmark" / "SciAgentArena" / "evaluations" / "dd" / "tasks_index.json"
SUMMARY = WORKSPACE / "results" / "c1" / "summary.json"
METRICS = ("executability", "validity", "correctness", "strategic_success")


def main() -> None:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    expected_ids = {entry["task_id"] for entry in index if entry.get("category") == "C1"}
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    tasks = summary["tasks"]
    actual_ids = {task["task_id"] for task in tasks}

    assert len(expected_ids) == 18, f"registry has {len(expected_ids)} C1 tasks, expected 18"
    assert summary["task_count"] == 18, summary["task_count"]
    assert len(tasks) == 18, len(tasks)
    assert actual_ids == expected_ids, {
        "missing": sorted(expected_ids - actual_ids),
        "extra": sorted(actual_ids - expected_ids),
    }
    assert len(actual_ids) == len(tasks), "duplicate task IDs in summary"

    for task in tasks:
        for metric in METRICS:
            value = float(task[metric])
            assert math.isfinite(value), (task["task_id"], metric, value)
            assert 0.0 <= value <= 1.0, (task["task_id"], metric, value)
        record = SUMMARY.parent / f"{task['task_id']}.json"
        assert record.is_file(), record

    calculated = sum(float(task["correctness"]) for task in tasks) / len(tasks)
    assert math.isclose(
        calculated,
        float(summary["mean_correctness"]),
        rel_tol=0.0,
        abs_tol=1e-12,
    ), (calculated, summary["mean_correctness"])
    print(
        "OK: 18/18 C1 tasks accounted for; all metrics finite and in [0, 1]; "
        f"mean correctness={calculated:.10f}"
    )


if __name__ == "__main__":
    main()
