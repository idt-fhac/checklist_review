"""REST API service layer for review runs."""

from __future__ import annotations

import json
import logging
import multiprocessing
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core import storage, task_persistence
from src.core.config_loader import list_pipelines, load_pipeline
from src.core.criteria import find_criteria_set_path, load_criteria_set_file
from src.core.task_manager import TaskManager, TaskStatus
from src.core.workspace import get_collections_dir, get_criteria_sets_dir
from src.review_workflow.engine.pipeline_loader import build_review_process_definition, load_pipeline_flow
from src.review_workflow.engine.run_paths import artifact_run_dir
from src.review_workflow.components.evaluators.criterion_evaluator.file_utils import (
    get_persona_evaluations_dir,
    get_persona_manifest_path,
)
from src.review_workflow.review_runner import run_review_subprocess

logger = logging.getLogger(__name__)


class ReviewServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def list_pipelines_manifest() -> List[Dict[str, Any]]:
    return list_pipelines()


def get_pipeline_manifest(pipeline_id: str) -> Dict[str, Any]:
    try:
        pipeline = load_pipeline(pipeline_id)
    except FileNotFoundError as exc:
        raise ReviewServiceError(str(exc), 404) from exc
    process_def = build_review_process_definition(pipeline_id, pipeline=pipeline)
    evaluation = process_def.get("evaluation") or {}
    return {
        "id": pipeline.get("id") or pipeline_id,
        "name": pipeline.get("name") or pipeline_id,
        "profile": pipeline.get("profile"),
        "stages": [next(iter(step.keys())) for step in (pipeline.get("stages") or []) if isinstance(step, dict)],
        "flow": load_pipeline_flow(pipeline_id),
        "evaluation_mode": evaluation.get("mode", "single"),
        "personas": evaluation.get("personas") or [],
        "merge_strategy": evaluation.get("merge_strategy"),
    }


def list_criteria_sets_manifest() -> List[Dict[str, Any]]:
    from src.core.workspace import get_workspace_dir

    return storage.list_criteria_sets(get_workspace_dir())


def _sync_running_tasks(collections_root: Path, collection_name: str) -> None:
    task_manager = TaskManager()
    for task in task_manager.get_tasks_for_collection(collection_name):
        if task.progress.status != TaskStatus.RUNNING:
            continue
        process = getattr(task, "process", None)
        if process is None or process.is_alive():
            continue
        file_progress = task_persistence.read_progress(collections_root, task.task_id)
        if not file_progress:
            continue
        task.progress.current = file_progress.get("current", task.progress.current)
        task.progress.total = file_progress.get("total", task.progress.total)
        task.progress.current_item = file_progress.get("current_item", "")
        status_val = file_progress.get("status", "running")
        task.progress.status = TaskStatus(status_val) if isinstance(status_val, str) else status_val
        task.progress.error = file_progress.get("error")
        if task.progress.status == TaskStatus.RUNNING:
            task.progress.status = TaskStatus.FAILED
            task.progress.error = task.progress.error or "Process exited unexpectedly"
        task.progress.results = file_progress.get("results", [])
        task.progress.log_messages = file_progress.get("log_messages", [])


def start_review(
    *,
    collection_name: str,
    pipeline_id: str,
    criteria_set_name: Optional[str] = None,
    artifact_ids: Optional[List[str]] = None,
    criteria_source_name: Optional[str] = None,
    reference_urls: Optional[List[str]] = None,
    skip_existing: bool = True,
) -> str:
    if not collection_name:
        raise ReviewServiceError("collection_name is required")
    if not pipeline_id:
        raise ReviewServiceError("pipeline_id is required")
    pipeline = load_pipeline(pipeline_id)
    has_extractor = any(
        isinstance(step, dict) and "criteria_extractor" in step for step in (pipeline.get("stages") or [])
    )
    if not criteria_set_name:
        if has_extractor:
            criteria_set_name = "extracted"
        else:
            raise ReviewServiceError("criteria_set_name is required")

    try:
        build_review_process_definition(pipeline_id)
    except FileNotFoundError as exc:
        raise ReviewServiceError(str(exc), 404) from exc
    except ValueError as exc:
        raise ReviewServiceError(str(exc), 400) from exc

    collections_root = Path(get_collections_dir())
    _sync_running_tasks(collections_root, collection_name)

    task_manager = TaskManager()
    running = task_manager.get_running_task_for_collection(collection_name)
    if running:
        raise ReviewServiceError(
            f"A review is already running for this collection (review_id={running.task_id})",
            409,
        )

    criteria_path = find_criteria_set_path(get_criteria_sets_dir(), criteria_set_name)
    if criteria_path is None and not has_extractor:
        raise ReviewServiceError(f"Criteria set '{criteria_set_name}' not found", 404)

    selected_artifacts = storage.list_selected_files(collections_root, collection_name)
    if artifact_ids:
        wanted = set(artifact_ids)
        selected_artifacts = [
            artifact
            for artifact in selected_artifacts
            if artifact.get("artifact_id") in wanted or artifact.get("filename") in wanted
        ]

    if skip_existing:
        existing = storage.list_evaluations(collections_root, collection_name, pipeline_id, criteria_set_name)
        processed = {item.get("filename") for item in existing if item.get("filename")}
        selected_artifacts = [
            artifact for artifact in selected_artifacts if artifact.get("filename") not in processed
        ]

    if not selected_artifacts:
        total = storage.list_selected_files(collections_root, collection_name)
        if not total:
            raise ReviewServiceError("No artifacts found in collection. Upload a draft with role=artifact.", 400)
        raise ReviewServiceError("No artifacts left to review", 400)

    if reference_urls is None:
        from src.web.api.collection_service import get_references

        reference_urls = get_references(collection_name)

    task_id = task_manager.create_task(
        collection_name=collection_name,
        pipeline_id=pipeline_id,
        criteria_set_name=criteria_set_name,
        artifacts=selected_artifacts,
    )
    task = task_manager.get_task(task_id)
    if not task:
        raise ReviewServiceError("Failed to create review task", 500)

    task_persistence.write_task_payload(
        collections_root,
        task_id,
        collection_name=collection_name,
        pipeline_id=pipeline_id,
        criteria_set_name=criteria_set_name,
        artifacts=selected_artifacts,
        criteria_source_name=criteria_source_name,
        reference_urls=reference_urls,
        progress={
            "current": task.progress.current,
            "total": task.progress.total,
            "current_item": task.progress.current_item,
            "status": task.progress.status.value,
            "error": task.progress.error,
            "started_at": task.progress.started_at.isoformat() if task.progress.started_at else None,
            "completed_at": None,
            "results": [],
            "log_messages": [],
        },
    )

    task.progress.status = TaskStatus.RUNNING
    task.process = multiprocessing.Process(
        target=run_review_subprocess,
        args=(task_id, str(collections_root)),
        daemon=False,
    )
    task.process.start()
    return task_id


def _load_task(review_id: str):
    collections_root = Path(get_collections_dir())
    payload = task_persistence.read_task_payload(collections_root, review_id)

    if payload and payload.get("collection_name"):
        _sync_running_tasks(collections_root, payload["collection_name"])

    task_manager = TaskManager()
    task = task_manager.get_task(review_id)
    if not task:
        task = task_persistence.task_view_from_file(collections_root, review_id)

    if task and payload and getattr(task, "process", None) is not None:
        if task.progress.status == TaskStatus.RUNNING:
            file_progress = task_persistence.read_progress(collections_root, review_id)
            if file_progress:
                task.progress = task_persistence.TaskView(review_id, file_progress).progress

    if not task and not payload:
        return None, None, collections_root

    return task, payload, collections_root


def get_review_status(review_id: str) -> Dict[str, Any]:
    task, payload, _collections_root = _load_task(review_id)
    if not task or not payload:
        raise ReviewServiceError("Review not found", 404)

    progress = task.progress
    return {
        "review_id": review_id,
        "status": progress.status.value if hasattr(progress.status, "value") else progress.status,
        "collection_name": payload.get("collection_name"),
        "pipeline_id": payload.get("pipeline_id"),
        "criteria_set_name": payload.get("criteria_set_name"),
        "criteria_source_name": payload.get("criteria_source_name"),
        "reference_urls": payload.get("reference_urls") or [],
        "current": progress.current,
        "total": progress.total,
        "current_item": progress.current_item or "",
        "error": progress.error,
        "started_at": _iso(progress.started_at),
        "completed_at": _iso(progress.completed_at),
        "results": progress.results or [],
        "log_messages": progress.log_messages or [],
    }


def cancel_review(review_id: str) -> Dict[str, Any]:
    task, payload, collections_root = _load_task(review_id)
    if not task or not payload:
        raise ReviewServiceError("Review not found", 404)

    if task.progress.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
        return {
            "review_id": review_id,
            "status": task.progress.status.value,
            "message": "Review is not running",
        }

    if hasattr(task, "stop_event") and task.stop_event is not None:
        task.stop_event.set()
    task_persistence.request_stop(collections_root, review_id)
    if getattr(task, "stop_event", None) is not None and task.progress.status == TaskStatus.PENDING:
        task.progress.status = TaskStatus.STOPPED
        task.progress.completed_at = datetime.now()

    return {
        "review_id": review_id,
        "status": task.progress.status.value,
        "message": "Cancel requested",
    }


def _read_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def build_review_report(review_id: str) -> Dict[str, Any]:
    task, payload, collections_root = _load_task(review_id)
    if not task or not payload:
        raise ReviewServiceError("Review not found", 404)

    collection_name = payload.get("collection_name")
    pipeline_id = payload.get("pipeline_id")
    criteria_set_name = payload.get("criteria_set_name")
    if not collection_name or not pipeline_id:
        raise ReviewServiceError("Review metadata is incomplete for this run", 422)
    status = get_review_status(review_id)

    artifact_reports: List[Dict[str, Any]] = []
    for artifact in payload.get("artifacts", []):
        filename = artifact.get("filename")
        artifact_id = artifact.get("artifact_id", filename)
        if not filename:
            continue

        evaluations = storage.load_evaluation(
            collections_root, collection_name, artifact_id, pipeline_id, criteria_set_name
        )
        if isinstance(evaluations, list):
            evaluation_items = evaluations
        elif isinstance(evaluations, dict):
            evaluation_items = list(evaluations.values())
        else:
            evaluation_items = []

        run_dir = artifact_run_dir(
            collections_root,
            collection_name,
            pipeline_id,
            filename,
            criteria_set_name,
        )
        outputs = storage.list_review_outputs(
            collections_root, collection_name, pipeline_id, criteria_set_name, artifact_id
        )
        output_entries = [
            {
                "name": item["name"],
                "type": item["type"],
                "path": f"/api/v1/reviews/{review_id}/artifacts/{artifact_id}/outputs/{item['name']}",
            }
            for item in outputs
        ]

        criteria_doc = None
        criteria_file = run_dir / "criteria.yaml"
        if criteria_file.exists():
            try:
                criteria_doc = load_criteria_set_file(criteria_file)
            except Exception:
                criteria_doc = None

        persona_manifest = _read_json_if_exists(
            get_persona_manifest_path(
                collection_name,
                pipeline_id,
                filename,
                criteria_set_name,
                collections_root,
            )
        )
        persona_evaluations = {}
        if persona_manifest:
            persona_dir = get_persona_evaluations_dir(
                collection_name,
                pipeline_id,
                filename,
                criteria_set_name,
                collections_root,
            )
            for persona_file in sorted(persona_dir.glob("*.json")):
                if persona_file.name == "manifest.json":
                    continue
                persona_evaluations[persona_file.stem] = _read_json_if_exists(persona_file)

        artifact_reports.append(
            {
                "artifact_id": artifact_id,
                "filename": filename,
                "evaluations": evaluation_items,
                "persona_manifest": persona_manifest,
                "persona_evaluations": persona_evaluations or None,
                "criteria": criteria_doc,
                "mapping": _read_json_if_exists(run_dir / "mapping.json"),
                "synthesis": _read_json_if_exists(run_dir / "synthesis.json"),
                "search_log": _read_json_if_exists(run_dir / "search_log.json"),
                "token_usage": _read_json_if_exists(run_dir / "token_usage.json"),
                "outputs": output_entries,
            }
        )

    return {
        **status,
        "artifacts": artifact_reports,
    }


def get_output_file_path(
    review_id: str,
    artifact_id: str,
    filename: str,
) -> Path:
    _, payload, collections_root = _load_task(review_id)
    if not payload:
        raise ReviewServiceError("Review not found", 404)

    outputs_dir = storage.get_review_outputs_dir(
        collections_root,
        payload["collection_name"],
        payload["pipeline_id"],
        payload["criteria_set_name"],
        artifact_id,
    )
    if not outputs_dir:
        raise ReviewServiceError("Outputs not found", 404)

    file_path = (outputs_dir / filename).resolve()
    if not str(file_path).startswith(str(outputs_dir.resolve())):
        raise ReviewServiceError("Invalid filename", 400)
    if not file_path.is_file():
        raise ReviewServiceError("File not found", 404)
    return file_path


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
