"""Shared paths for per-artifact review run directories."""

from __future__ import annotations

from pathlib import Path

from src.core.criteria import criteria_set_stem


def _slug(name: str) -> str:
    return name.strip().replace(" ", "_").lower() or "process"


def artifact_run_dir(
    collections_root: Path,
    collection_name: str,
    pipeline_name: str,
    artifact_name: str,
    criteria_set_name: str | None = None,
) -> Path:
    run_dir = Path(collections_root) / _slug(collection_name) / "review_runs" / _slug(pipeline_name)
    if criteria_set_name:
        run_dir = run_dir / _slug(criteria_set_stem(criteria_set_name))
    return run_dir / artifact_name
