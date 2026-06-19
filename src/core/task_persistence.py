"""
File-based persistence for review tasks so that:
- The review can run in a separate process (survives Flask reload).
- Progress can be read after parent process restarts.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from src.core.task_manager import TaskStatus

logger = logging.getLogger(__name__)


def _as_datetime(v: Any):
    """Return value as datetime if it's an ISO string, else return as-is."""
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v
    if isinstance(v, str):
        try:
            from datetime import datetime
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            pass
    return v


class _ProgressView:
    """Minimal progress object built from a dict (e.g. from file) for API responses."""

    def __init__(self, d: Dict[str, Any]):
        self.current = d.get("current", 0)
        self.total = d.get("total", 0)
        self.current_item = d.get("current_item") or ""
        status_val = d.get("status", "pending")
        self.status = TaskStatus(status_val) if isinstance(status_val, str) else status_val
        self.error = d.get("error")
        self.started_at = _as_datetime(d.get("started_at"))
        self.completed_at = _as_datetime(d.get("completed_at"))
        self.results = d.get("results") or []
        self.log_messages = d.get("log_messages") or []


class TaskView:
    """Minimal task-like object built from file for API when task is not in TaskManager."""

    def __init__(self, task_id: str, progress: Dict[str, Any]):
        self.task_id = task_id
        self.progress = _ProgressView(progress)

TASK_DIR_NAME = ".review_tasks"


def _task_dir(collections_root: Path) -> Path:
    # collections_root is typically workspaces/guest/collections
    # We want .review_tasks to be in workspaces/guest/.review_tasks
    base_dir = Path(collections_root).parent if Path(collections_root).name == "collections" else Path(collections_root)
    d = base_dir / TASK_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def task_file_path(collections_root: Path, task_id: str) -> Path:
    return _task_dir(collections_root) / f"{task_id}.json"


def stop_file_path(collections_root: Path, task_id: str) -> Path:
    return _task_dir(collections_root) / f"{task_id}.stop"


def write_task_payload(
    collections_root: Path,
    task_id: str,
    *,
    collection_name: str,
    pipeline_id: str,
    criteria_set_name: str,
    artifacts: list,
    progress: Optional[Dict[str, Any]] = None,
) -> Path:
    path = task_file_path(collections_root, task_id)
    payload = {
        "task_id": task_id,
        "collection_name": collection_name,
        "pipeline_id": pipeline_id,
        "criteria_set_name": criteria_set_name,
        "artifacts": artifacts,
        "progress": progress or {
            "current": 0,
            "total": len(artifacts),
            "current_item": "",
            "status": "pending",
            "error": None,
            "started_at": None,
            "completed_at": None,
            "results": [],
            "log_messages": [],
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return path


def read_task_payload(collections_root: Path, task_id: str) -> Optional[Dict[str, Any]]:
    """Read task payload from disk (used by child process)."""
    path = task_file_path(collections_root, task_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read task file {path}: {e}")
        return None


def write_progress(
    collections_root: Path,
    task_id: str,
    progress: Dict[str, Any],
) -> None:
    """Update only progress in the task file (used by child process)."""
    path = task_file_path(collections_root, task_id)
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        payload["progress"] = progress
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"Failed to write progress for {task_id}: {e}")


def read_progress(collections_root: Path, task_id: str) -> Optional[Dict[str, Any]]:
    """Read progress from task file (for parent to sync or serve after reload)."""
    payload = read_task_payload(collections_root, task_id)
    if payload is None:
        return None
    return payload.get("progress")


def request_stop(collections_root: Path, task_id: str) -> None:
    """Create stop file so child process can notice and stop."""
    path = stop_file_path(collections_root, task_id)
    path.touch()


def stop_requested(collections_root: Path, task_id: str) -> bool:
    """Check if stop was requested (used by child process)."""
    return stop_file_path(collections_root, task_id).exists()


def cleanup_task_files(collections_root: Path, task_id: str) -> None:
    """Remove task and stop files for a task."""
    task_file_path(collections_root, task_id).unlink(missing_ok=True)
    stop_file_path(collections_root, task_id).unlink(missing_ok=True)


def task_view_from_file(collections_root: Path, task_id: str) -> Optional[TaskView]:
    """Build a TaskView from the task file (for status API after reload or when task is in child process)."""
    payload = read_task_payload(collections_root, task_id)
    if not payload or "progress" not in payload:
        return None
    return TaskView(task_id=task_id, progress=payload["progress"])
