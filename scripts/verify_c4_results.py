"""Independently verify completeness, scales, and arithmetic of C4 results."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from rdkit import Chem


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_DD_ROOT = WORKSPACE / "benchmark" / "SciAgentArena" / "evaluations" / "dd"
DEFAULT_SUMMARY = WORKSPACE / "results" / "c4" / "summary.json"
DEFAULT_AGENT = WORKSPACE / "agents" / "c4_safety.py"
DEFAULT_ALERTS = WORKSPACE / "agents" / "c4_alert_catalog.json"
PERCENT_SCALE_TASKS = {"reg_05_cyanide_trap"}


def _close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12)


def _assert_metric(task: dict[str, Any], metric: str, scale: float) -> None:
    raw = float(task[metric])
    normalized = float(task[f"{metric}_normalized"])
    recorded_scale = float(task[f"{metric}_scale"])
    assert math.isfinite(raw), (task["task_id"], metric, raw)
    assert 0.0 <= raw <= scale, (task["task_id"], metric, raw, scale)
    assert recorded_scale == scale, (task["task_id"], metric, recorded_scale, scale)
    assert math.isfinite(normalized) and 0.0 <= normalized <= 1.0
    assert _close(normalized, raw / scale), (task["task_id"], metric, raw, normalized)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dd-root", type=Path, default=DEFAULT_DD_ROOT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--agent", type=Path, default=DEFAULT_AGENT)
    parser.add_argument("--alerts", type=Path, default=DEFAULT_ALERTS)
    args = parser.parse_args()

    index_path = args.dd_root.resolve() / "tasks_index.json"
    summary_path = args.summary.resolve()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    expected_ids = {entry["task_id"] for entry in index if entry.get("category") == "C4"}
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    tasks = summary["tasks"]
    actual_ids = {task["task_id"] for task in tasks}

    assert len(expected_ids) == 6, f"registry has {len(expected_ids)} C4 tasks, expected 6"
    assert summary["task_count"] == 6, summary["task_count"]
    assert len(tasks) == 6, len(tasks)
    assert len(actual_ids) == len(tasks), "duplicate task IDs in summary"
    assert actual_ids == expected_ids, {
        "missing": sorted(expected_ids - actual_ids),
        "extra": sorted(actual_ids - expected_ids),
    }

    for task in tasks:
        task_id = task["task_id"]
        for metric in ("executability", "validity"):
            value = float(task[metric])
            assert math.isfinite(value) and 0.0 <= value <= 1.0, (task_id, metric, value)
        scale = 100.0 if task_id in PERCENT_SCALE_TASKS else 1.0
        _assert_metric(task, "correctness", scale)
        _assert_metric(task, "strategic_success", scale)
        record_path = summary_path.parent / f"{task_id}.json"
        assert record_path.is_file(), record_path
        record = json.loads(record_path.read_text(encoding="utf-8"))["score"]
        assert _close(float(record["correctness"]), float(task["correctness"]))
        assert _close(float(record["strategic_success"]), float(task["strategic_success"]))

    expected_means = {
        "mean_executability": sum(float(t["executability"]) for t in tasks) / 6,
        "mean_validity": sum(float(t["validity"]) for t in tasks) / 6,
        "mean_correctness_normalized": sum(float(t["correctness_normalized"]) for t in tasks) / 6,
        "mean_strategic_success_normalized": sum(
            float(t["strategic_success_normalized"]) for t in tasks
        )
        / 6,
    }
    for key, calculated in expected_means.items():
        assert _close(calculated, float(summary[key])), (key, calculated, summary[key])

    source = args.agent.resolve().read_text(encoding="utf-8").lower()
    for forbidden in ("scorers", "ground_truth", "toxalerts_ground_truth"):
        assert forbidden not in source, f"agent source references forbidden runtime data: {forbidden}"
    rules = json.loads(args.alerts.resolve().read_text(encoding="utf-8"))
    assert len(rules) == 104, len(rules)
    assert len({(str(name), str(pattern)) for name, pattern in rules}) == len(rules)
    invalid_smarts = [str(name) for name, pattern in rules if Chem.MolFromSmarts(str(pattern)) is None]
    assert not invalid_smarts, f"invalid SMARTS rules: {invalid_smarts}"

    print(
        "OK: 6/6 C4 tasks accounted for; raw scales and normalized arithmetic verified; "
        f"mean normalized correctness={expected_means['mean_correctness_normalized']:.10f}"
    )


if __name__ == "__main__":
    main()
