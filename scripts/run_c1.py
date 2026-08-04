"""Run the deterministic baseline once against all official C1 batch tasks."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[1]
DD_ROOT = WORKSPACE / "benchmark" / "SciAgentArena" / "evaluations" / "dd"
PYTHON = WORKSPACE / ".venv" / "Scripts" / "python.exe"
EVALUATOR = DD_ROOT / "evaluate.py"
TASK_INDEX = DD_ROOT / "tasks_index.json"
AGENT = WORKSPACE / "agents" / "c1_baseline.py"


def _load_tasks() -> list[dict[str, Any]]:
    with TASK_INDEX.open(encoding="utf-8") as handle:
        index = json.load(handle)
    return [entry for entry in index if entry.get("category") == "C1"]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "task_id",
        "executability",
        "validity",
        "correctness",
        "strategic_success",
        "wall_time_seconds",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({key: row.get(key) for key in fieldnames} for row in rows)


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    return sum(float(row.get(key, 0.0)) for row in rows) / len(rows) if rows else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=WORKSPACE / "results" / "c1",
        help="Directory for per-task scores and aggregate summaries.",
    )
    args = parser.parse_args()
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    required = [PYTHON, EVALUATOR, TASK_INDEX, AGENT]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        print(f"Missing required paths: {missing}", file=sys.stderr)
        return 2

    tasks = _load_tasks()
    results: list[dict[str, Any]] = []
    for position, task in enumerate(tasks, start=1):
        task_id = task["task_id"]
        result_path = out_dir / f"{task_id}.json"
        env = os.environ.copy()
        env["C1_TASK_ID"] = task_id
        command = [
            str(PYTHON),
            str(EVALUATOR),
            "run",
            task_id,
            str(AGENT),
            "--out",
            str(result_path),
        ]
        print(f"[{position:02d}/{len(tasks):02d}] {task_id}", flush=True)
        completed = subprocess.run(
            command,
            cwd=DD_ROOT,
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
        results.append(result)
        print(
            "  "
            f"exec={result.get('executability', 0):.3f} "
            f"valid={result.get('validity', 0):.3f} "
            f"correct={result.get('correctness', 0):.3f}",
            flush=True,
        )

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "task_count": len(results),
        "aggregation": "unweighted arithmetic mean across the 18 C1 tasks",
        "mean_executability": _mean(results, "executability"),
        "mean_validity": _mean(results, "validity"),
        "mean_correctness": _mean(results, "correctness"),
        "mean_strategic_success": _mean(results, "strategic_success"),
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
