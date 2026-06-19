"""Background review execution (subprocess entry point)."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from src.core import task_persistence as tp
from src.core.task_manager import TaskStatus
from src.review_workflow.engine.pipeline_loader import build_review_process_definition
from src.review_workflow.engine.review_process import ReviewProcess

logger = logging.getLogger(__name__)


def run_review_subprocess(task_id: str, collections_root: Path | str) -> None:
    """
    Run a review task in a separate process using file-based progress persistence.
    """
    collections_root = Path(collections_root)
    payload = tp.read_task_payload(collections_root, task_id)
    if not payload:
        logger.error("Subprocess: task %s payload not found in file", task_id)
        return

    artifacts = payload.get("artifacts", [])
    collection_name = payload.get("collection_name", "")
    pipeline_id = payload.get("pipeline_id", "")
    criteria_set_name = payload.get("criteria_set_name", "")
    criteria_source_name = payload.get("criteria_source_name")
    reference_urls = payload.get("reference_urls") or []

    if tp.stop_requested(collections_root, task_id):
        logger.info("Task %s stop requested before start", task_id)
        tp.write_progress(
            collections_root,
            task_id,
            {
                **payload.get("progress", {}),
                "status": TaskStatus.STOPPED.value,
                "completed_at": datetime.now().isoformat(),
            },
        )
        return

    progress = dict(payload.get("progress", {}))
    progress["status"] = TaskStatus.RUNNING.value
    progress["started_at"] = progress.get("started_at") or datetime.now().isoformat()
    progress["total"] = len(artifacts)
    tp.write_progress(collections_root, task_id, progress)

    stop_event = threading.Event()

    def stop_poller():
        while not stop_event.is_set():
            if tp.stop_requested(collections_root, task_id):
                stop_event.set()
                return
            time.sleep(0.5)

    threading.Thread(target=stop_poller, daemon=True).start()

    def add_log_message(message: str, level: str = "info"):
        progress["log_messages"] = progress.get("log_messages") or []
        progress["log_messages"].append(
            {
                "timestamp": datetime.now().isoformat(),
                "message": message,
                "level": level,
            }
        )
        tp.write_progress(collections_root, task_id, progress)

    if criteria_set_name and ("/" in criteria_set_name or "\\" in criteria_set_name):
        criteria_set_name = Path(criteria_set_name).stem

    try:
        review_process_def = build_review_process_definition(pipeline_id)
    except Exception as exc:
        logger.error("Error loading pipeline: %s", exc, exc_info=True)
        add_log_message(f"Error: Failed to load pipeline: {exc}", "error")
        progress["status"] = TaskStatus.FAILED.value
        progress["error"] = str(exc)
        progress["completed_at"] = datetime.now().isoformat()
        tp.write_progress(collections_root, task_id, progress)
        return

    for idx, artifact in enumerate(artifacts):
        if stop_event.is_set():
            progress["status"] = TaskStatus.STOPPED.value
            progress["completed_at"] = datetime.now().isoformat()
            progress["current"] = idx
            tp.write_progress(collections_root, task_id, progress)
            return

        artifact_name = artifact.get("filename")
        if not artifact_name:
            continue

        progress["current"] = idx
        progress["current_item"] = artifact_name
        tp.write_progress(collections_root, task_id, progress)

        try:
            process_instance = ReviewProcess(
                review_process_def,
                stop_event=stop_event,
                log_callback=add_log_message,
                collections_root=collections_root,
            )
            run_result = process_instance.execute(
                collection_name=collection_name,
                artifact_name=artifact_name,
                criteria_set_name=criteria_set_name,
                artifact_index=idx + 1,
                total_artifacts=len(artifacts),
                criteria_source_name=criteria_source_name,
                reference_urls=reference_urls,
            )
            if stop_event.is_set():
                progress["status"] = TaskStatus.STOPPED.value
                progress["completed_at"] = datetime.now().isoformat()
                progress["current"] = idx + 1
                tp.write_progress(collections_root, task_id, progress)
                return
            progress["results"] = progress.get("results") or []
            result_entry = {
                "artifact_id": artifact.get("artifact_id", artifact_name),
                "filename": artifact_name,
                "status": "completed",
            }
            if run_result and run_result.get("token_usage"):
                result_entry["token_usage"] = run_result["token_usage"]
            progress["results"].append(result_entry)
            tp.write_progress(collections_root, task_id, progress)
        except InterruptedError:
            progress["status"] = TaskStatus.STOPPED.value
            progress["completed_at"] = datetime.now().isoformat()
            add_log_message("Review stopped by user", "warning")
            progress["results"] = progress.get("results") or []
            progress["results"].append(
                {
                    "artifact_id": artifact.get("artifact_id", artifact_name),
                    "filename": artifact_name,
                    "status": "stopped",
                    "error": "Stopped by user",
                }
            )
            tp.write_progress(collections_root, task_id, progress)
            return
        except Exception as exc:
            logger.error("Failed to process %s: %s", artifact_name, exc, exc_info=True)
            add_log_message(f"Error processing artifact: {exc}", "error")
            progress["results"] = progress.get("results") or []
            progress["results"].append(
                {
                    "artifact_id": artifact.get("artifact_id", artifact_name),
                    "filename": artifact_name,
                    "status": "failed",
                    "error": str(exc),
                }
            )
            tp.write_progress(collections_root, task_id, progress)
            if stop_event.is_set():
                progress["status"] = TaskStatus.STOPPED.value
                progress["completed_at"] = datetime.now().isoformat()
                tp.write_progress(collections_root, task_id, progress)
                return

    progress["status"] = TaskStatus.COMPLETED.value
    progress["current"] = len(artifacts)
    progress["completed_at"] = datetime.now().isoformat()
    tp.write_progress(collections_root, task_id, progress)
    logger.info("Task %s completed successfully", task_id)
