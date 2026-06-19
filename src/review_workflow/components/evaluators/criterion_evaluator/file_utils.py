import json
from pathlib import Path
from typing import Dict, Any

from src.review_workflow.components.evaluators.criterion_evaluator.helpers import get_project_root, slug


def get_artifact_file_paths(
    collection_name: str,
    pipeline_name: str,
    artifact_name: str,
    criteria_set_name: str | None = None,
    collections_root: Path | None = None,
):
    if collections_root is None:
        collections_root = get_project_root() / "workspaces" / "guest" / "collections"
    artifact_dir = Path(collections_root) / slug(collection_name) / "review_runs" / slug(pipeline_name)
    if criteria_set_name:
        criteria_clean = criteria_set_name.removesuffix(".json")
        artifact_dir = artifact_dir / slug(criteria_clean)
    artifact_dir = artifact_dir / artifact_name
    return artifact_dir / "artifact_content.json", artifact_dir / "artifact_content.md"


def get_evaluations_file_path(
    collection_name: str,
    pipeline_name: str,
    artifact_name: str,
    criteria_set_name: str | None = None,
    collections_root: Path | None = None,
) -> Path:
    if collections_root is None:
        collections_root = get_project_root() / "workspaces" / "guest" / "collections"
    artifact_dir = Path(collections_root) / slug(collection_name) / "review_runs" / slug(pipeline_name)
    if criteria_set_name:
        criteria_clean = criteria_set_name.removesuffix(".json")
        artifact_dir = artifact_dir / slug(criteria_clean)
    artifact_dir = artifact_dir / artifact_name
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir / "evaluations.json"


def load_existing_evaluations(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = json.load(f)
            if isinstance(content, list):
                return {item.get("criterion_id"): item for item in content}
            return content if isinstance(content, dict) else {}
    except (json.JSONDecodeError, IOError):
        return {}


def save_evaluations(path: Path, evaluations: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(list(evaluations.values()), f, indent=2)
