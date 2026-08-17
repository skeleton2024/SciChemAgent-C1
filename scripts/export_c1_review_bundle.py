"""Export deterministic C1 solutions and compact public execution trajectories."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_DD_ROOT = WORKSPACE / "benchmark" / "SciAgentArena" / "evaluations" / "dd"
DEFAULT_OUT = WORKSPACE / "review" / "c1"
AGENT = WORKSPACE / "agents" / "c1_baseline.py"
FORBIDDEN_PUBLIC_TEXT = (
    "ground_truth",
    "scoring_logic",
    "wall_time_seconds",
    "\\users\\",
    "/home/",
)


def _select_python(workspace: Path) -> Path:
    candidates = (
        workspace / ".venv" / "Scripts" / "python.exe",
        workspace / ".venv" / "bin" / "python",
    )
    return next((path for path in candidates if path.is_file()), Path(sys.executable))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )


def _assert_public(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()
    matches = [token for token in FORBIDDEN_PUBLIC_TEXT if token in lowered]
    if matches:
        raise ValueError(f"{path} contains non-public tokens: {matches}")


def _benchmark_revision(dd_root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(dd_root.parents[1]), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _load_c1_entries(dd_root: Path) -> list[dict[str, Any]]:
    with (dd_root / "tasks_index.json").open(encoding="utf-8") as handle:
        entries = json.load(handle)
    c1_entries = [entry for entry in entries if entry.get("category") == "C1"]
    if len(c1_entries) != 18:
        raise ValueError(f"expected 18 C1 tasks, found {len(c1_entries)}")
    return c1_entries


def _agent_environment(task: dict[str, Any], task_id: str) -> dict[str, str]:
    env = {
        name: os.environ[name]
        for name in ("PATH", "PATHEXT", "SYSTEMROOT", "TEMP", "TMP", "WINDIR")
        if name in os.environ
    }
    env["PYTHONUTF8"] = "1"
    env["C1_TASK_ID"] = task_id
    env["AGENT4S_INPUT_JSON"] = json.dumps(task.get("input", {}), ensure_ascii=False)
    env["AGENT4S_NO_NETWORK"] = "1"
    return env


def _run_agent(
    python: Path,
    dd_root: Path,
    task: dict[str, Any],
    task_id: str,
) -> tuple[Any, dict[str, Any]]:
    env = _agent_environment(task, task_id)
    timeout = int(task.get("constraints", {}).get("timeout_seconds", 30))
    try:
        completed = subprocess.run(
            [str(python), str(AGENT)],
            cwd=dd_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{task_id}: agent timed out after {timeout}s") from exc
    if completed.returncode != 0:
        raise RuntimeError(
            f"{task_id}: agent exited {completed.returncode}: {completed.stderr[-500:]}"
        )
    try:
        solution = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{task_id}: stdout is not valid JSON") from exc
    execution = {
        "returncode": completed.returncode,
        "timed_out": False,
        "stderr_empty": not bool(completed.stderr.strip()),
    }
    return solution, execution


def export_bundle(dd_root: Path, out_dir: Path) -> dict[str, Any]:
    python = _select_python(WORKSPACE)
    required = [python, AGENT, dd_root / "tasks_index.json"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing required files: {missing}")

    agent_hash = _sha256(AGENT)
    artifacts: list[dict[str, str]] = []
    for position, entry in enumerate(_load_c1_entries(dd_root), start=1):
        task_id = str(entry["task_id"])
        task_path = dd_root / str(entry["task_path"])
        with task_path.open(encoding="utf-8") as handle:
            task = json.load(handle)
        if task.get("id") != task_id:
            raise ValueError(f"task id mismatch for {task_path}")

        print(f"[{position:02d}/18] {task_id}", flush=True)
        solution, execution = _run_agent(python, dd_root, task, task_id)
        solution_path = out_dir / "solutions" / f"{task_id}.json"
        _write_json(solution_path, {"task_id": task_id, "solution": solution})
        _assert_public(solution_path)

        trajectory_path = out_dir / "trajectories" / f"{task_id}.json"
        trajectory = {
            "task_id": task_id,
            "execution_model": "deterministic_single_step",
            "events": [
                {
                    "step": 1,
                    "event": "task_received",
                    "prompt": task.get("prompt", ""),
                    "input": task.get("input", {}),
                },
                {
                    "step": 2,
                    "event": "agent_executed",
                    "entrypoint": "agents/c1_baseline.py",
                    "agent_sha256": agent_hash,
                    "network_used": False,
                    **execution,
                },
                {
                    "step": 3,
                    "event": "solution_emitted",
                    "format": "json_stdout",
                    "path": f"solutions/{task_id}.json",
                    "sha256": _sha256(solution_path),
                },
            ],
        }
        _write_json(trajectory_path, trajectory)
        _assert_public(trajectory_path)
        artifacts.append(
            {
                "task_id": task_id,
                "solution": f"solutions/{task_id}.json",
                "solution_sha256": _sha256(solution_path),
                "trajectory": f"trajectories/{task_id}.json",
                "trajectory_sha256": _sha256(trajectory_path),
            }
        )

    manifest = {
        "schema_version": 1,
        "category": "C1",
        "task_count": len(artifacts),
        "benchmark_revision": _benchmark_revision(dd_root),
        "agent": "agents/c1_baseline.py",
        "agent_sha256": agent_hash,
        "execution_model": "deterministic_single_step",
        "network_used": False,
        "artifacts": artifacts,
    }
    manifest_path = out_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    _assert_public(manifest_path)
    return manifest


def verify_bundle(out_dir: Path) -> dict[str, Any]:
    manifest_path = out_dir / "manifest.json"
    with manifest_path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    artifacts = manifest.get("artifacts", [])
    if manifest.get("task_count") != 18 or len(artifacts) != 18:
        raise ValueError("review manifest must contain exactly 18 C1 tasks")
    task_ids = [entry.get("task_id") for entry in artifacts]
    if len(set(task_ids)) != 18:
        raise ValueError("review manifest contains duplicate task ids")
    for entry in artifacts:
        for kind in ("solution", "trajectory"):
            path = out_dir / str(entry[kind])
            if not path.is_file():
                raise FileNotFoundError(path)
            if _sha256(path) != entry[f"{kind}_sha256"]:
                raise ValueError(f"hash mismatch: {path}")
            _assert_public(path)
    _assert_public(manifest_path)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dd-root", type=Path, default=DEFAULT_DD_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify an existing bundle without executing the agent.",
    )
    args = parser.parse_args()
    out_dir = args.out.resolve()
    manifest = verify_bundle(out_dir) if args.check else export_bundle(args.dd_root.resolve(), out_dir)
    print(json.dumps({"category": "C1", "task_count": manifest["task_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
