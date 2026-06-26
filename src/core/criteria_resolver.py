"""Resolve criteria set files from collection-local or workspace storage."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.core.criteria import (
    criteria_set_stem,
    find_criteria_set_path,
    load_criteria_set_file,
)
from src.core.storage import _collection_dir


def collection_criteria_path(
    collections_root: Path,
    collection_name: str,
    criteria_set_name: str,
) -> Path:
    collection_dir = _collection_dir(collections_root, collection_name, create=False)
    return collection_dir / "criteria" / f"{criteria_set_stem(criteria_set_name)}.yaml"


def resolve_criteria_path(
    collections_root: Path,
    collection_name: str,
    criteria_set_name: str,
    workspace_criteria_dir: Path,
) -> Optional[Path]:
    local_path = collection_criteria_path(
        collections_root, collection_name, criteria_set_name
    )
    if local_path.exists():
        return local_path
    return find_criteria_set_path(workspace_criteria_dir, criteria_set_name)


def load_criteria_for_review(
    collections_root: Path,
    collection_name: str,
    criteria_set_name: str,
    workspace_criteria_dir: Path,
):
    path = resolve_criteria_path(
        collections_root,
        collection_name,
        criteria_set_name,
        workspace_criteria_dir,
    )
    if path is None:
        return None
    return load_criteria_set_file(path)
