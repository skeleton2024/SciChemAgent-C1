"""Run the deterministic agent once against all six official C4 tasks."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_DD_ROOT = WORKSPACE / "benchmark" / "SciAgentArena" / "evaluations" / "dd"
AGENT = WORKSPACE / "agents" / "c4_safety.py"
PERCENT_SCALE_TASKS = {"reg_05_cyanide_trap"}


def _select_python(workspace: Path, fallback: Path | None = None) -> Path:
    candidates = (
        workspace / ".venv" / "Scripts" / "python.exe",
        workspace / ".venv" / "bin" / "python",
    )
    return next(
        (path for path in candidates if path.is_file()),
        Path(fallback or sys.executable),
    )


PYTHON = _select_python(WORKSPACE)


def _load_tasks(task_index: Path) -> list[dict[str, Any]]:
    with task_index.open(encoding="utf-8") as handle:
        index = json.load(handle)
    return [entry for entry in index if entry.get("category") == "C4"]


def _scale(task_id: str) -> float:
    return 100.0 if task_id in PERCENT_SCALE_TASKS else 1.0


def _normalized(value: Any, scale: float) -> float:
    numeric = float(value or 0.0)
    result = numeric / scale
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"metric {numeric!r} is outside the declared 0..{scale:g} scale")
    return result


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    return sum(float(row[key]) for row in rows) / len(rows) if rows else 0.0


def _summary_row(result: dict[str, Any], scale: float) -> dict[str, Any]:
    row = {
        key: result[key]
        for key in (
            "task_id",
            "executability",
            "validity",
            "correctness",
            "strategic_success",
        )
    }
    row["correctness_scale"] = scale
    row["correctness_normalized"] = _normalized(result.get("correctness", 0.0), scale)
    row["strategic_success_scale"] = scale
    row["strategic_success_normalized"] = _normalized(
        result.get("strategic_success", 0.0),
        scale,
    )
    return row


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "task_id",
        "executability",
        "validity",
        "correctness",
        "correctness_scale",
        "correctness_normalized",
        "strategic_success",
        "strategic_success_scale",
        "strategic_success_normalized",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({key: row.get(key) for key in fieldnames} for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=WORKSPACE / "results" / "c4",
        help="Directory for per-task scores and aggregate summaries.",
    )
    parser.add_argument(
        "--dd-root",
        type=Path,
        default=DEFAULT_DD_ROOT,
        help="SciAgentArena evaluations/dd directory (defaults to the pinned local checkout).",
    )
    args = parser.parse_args()
    out_dir = args.out.resolve()
    dd_root = args.dd_root.resolve()
    evaluator = dd_root / "evaluate.py"
    task_index = dd_root / "tasks_index.json"
    out_dir.mkdir(parents=True, exist_ok=True)

    required = [PYTHON, evaluator, task_index, AGENT, AGENT.with_name("c4_alert_catalog.json")]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        print(f"Missing required paths: {missing}", file=sys.stderr)
        return 2

    tasks = _load_tasks(task_index)
    if len(tasks) != 6:
        print(f"Expected six C4 tasks, found {len(tasks)}", file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    for position, task in enumerate(tasks, start=1):
        task_id = task["task_id"]
        result_path = out_dir / f"{task_id}.json"
        env = os.environ.copy()
        env["C4_TASK_ID"] = task_id
        command = [
            str(PYTHON),
            str(evaluator),
            "run",
            task_id,
            str(AGENT),
            "--out",
            str(result_path),
        ]
        print(f"[{position:02d}/{len(tasks):02d}] {task_id}", flush=True)
        completed = subprocess.run(
            command,
            cwd=dd_root,
            env=env,
            capture_output=True,
            text=True,
        )
        log_path = out_dir / f"{task_id}.log"
        log_path.write_text(
            completed.stdout + ("\nSTDERR:\n" + completed.stderr if completed.stderr else ""),
            encoding="utf-8",
        )
        if completed.returncode != 0 or not result_path.exists():
            print(f"  evaluator failed; see {log_path}", file=sys.stderr)
            return completed.returncode or 1
        with result_path.open(encoding="utf-8") as handle:
            document = json.load(handle)
        result = document.get("score", document)
        missing_metrics = [
            key
            for key in ("task_id", "executability", "validity", "correctness", "strategic_success")
            if key not in result
        ]
        if missing_metrics:
            print(
                f"  evaluator record is missing {missing_metrics}; see {result_path} and {log_path}",
                file=sys.stderr,
            )
            return 1
        if str(result["task_id"]) != task_id:
            print(
                f"  evaluator returned task_id={result['task_id']!r}, expected {task_id!r}",
                file=sys.stderr,
            )
            return 1
        scale = _scale(task_id)
        summary_row = _summary_row(result, scale)
        results.append(summary_row)
        print(
            "  "
            f"exec={float(result.get('executability', 0)):.3f} "
            f"valid={float(result.get('validity', 0)):.3f} "
            f"correct_raw={float(result.get('correctness', 0)):.4f} "
            f"correct_norm={summary_row['correctness_normalized']:.4f}",
            flush=True,
        )

    summary = {
        "task_count": len(results),
        "aggregation": (
            "unweighted arithmetic mean across six C4 tasks after explicit per-task "
            "normalization to [0,1]; reg_05 raw correctness and strategic_success are percentages"
        ),
        "mean_executability": _mean(results, "executability"),
        "mean_validity": _mean(results, "validity"),
        "mean_correctness_normalized": _mean(results, "correctness_normalized"),
        "mean_strategic_success_normalized": _mean(results, "strategic_success_normalized"),
        "tasks": results,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_csv(out_dir / "summary.csv", results)
    print(json.dumps({key: value for key, value in summary.items() if key != "tasks"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
