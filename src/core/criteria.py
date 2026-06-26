"""Criteria set schema and YAML persistence."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

CRITERIA_SET_SCHEMA_VERSION = 1
CRITERIA_SET_EXT = ".yaml"

CriteriaInput = Union[Dict[str, Any], Path]


def criteria_set_stem(name: str) -> str:
    for suffix in (".yaml", ".yml", ".json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def criteria_set_path(directory: Path, name: str) -> Path:
    return directory / f"{criteria_set_stem(name)}{CRITERIA_SET_EXT}"


def find_criteria_set_path(directory: Path, name: str) -> Optional[Path]:
    path = criteria_set_path(directory, name)
    return path if path.exists() else None


def normalize_criterion(raw: Any, index: int) -> Dict[str, Any]:
    if isinstance(raw, str):
        return {
            "id": f"req-{index + 1}",
            "description": raw,
            "scoring_type": "checklist",
        }
    if not isinstance(raw, dict):
        return {
            "id": f"req-{index + 1}",
            "description": str(raw),
            "scoring_type": "checklist",
        }

    criterion_id = raw.get("id") or f"req-{index + 1}"
    description = raw.get("description") or ""
    normalized: Dict[str, Any] = {
        "id": str(criterion_id),
        "description": str(description),
        "scoring_type": raw.get("scoring_type", "checklist"),
    }
    for key in ("category", "weight", "mandatory", "source_ref"):
        if raw.get(key) is not None:
            normalized[key] = raw[key]
    return normalized


def load_criteria_set(
    data: CriteriaInput, *, name: Optional[str] = None
) -> Dict[str, Any]:
    if isinstance(data, Path):
        payload = _load_yaml_dict(data)
        name = name or payload.get("name") or data.stem
    elif isinstance(data, dict):
        payload = data
        name = name or payload.get("name")
    else:
        raise ValueError("Criteria set must be a dict or file path")

    schema_version = payload.get("schema_version")
    if schema_version is not None and schema_version != CRITERIA_SET_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported criteria set schema_version {schema_version!r} "
            f"(expected {CRITERIA_SET_SCHEMA_VERSION})"
        )

    raw_items = payload.get("criteria")
    if not isinstance(raw_items, list):
        raise ValueError("Criteria set must contain a 'criteria' array")

    criteria = [normalize_criterion(item, i) for i, item in enumerate(raw_items)]
    criteria = [c for c in criteria if c.get("description")]

    return {
        "name": name or "criteria_set",
        "created_at": payload.get("created_at") or datetime.utcnow().isoformat(),
        "criteria": criteria,
        "source": payload.get("source"),
    }


def load_criteria_set_file(path: Path) -> Dict[str, Any]:
    return load_criteria_set(path, name=path.stem)


def criteria_set_document(
    criteria_set: Dict[str, Any],
    *,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    doc: Dict[str, Any] = {
        "schema_version": CRITERIA_SET_SCHEMA_VERSION,
        "name": criteria_set.get("name") or "criteria_set",
        "created_at": criteria_set.get("created_at") or datetime.utcnow().isoformat(),
        "criteria": criteria_set.get("criteria") or [],
    }
    for key in ("source", "generated_at", "artifact_id", "title"):
        val = (extra or {}).get(key) if extra else None
        if val is None:
            val = criteria_set.get(key)
        if val is not None:
            doc[key] = val
    return doc


def save_criteria_set_file(
    path: Path, criteria_set: Dict[str, Any], **extra: Any
) -> Dict[str, Any]:
    normalized = load_criteria_set(
        criteria_set_document(criteria_set, extra=extra), name=criteria_set.get("name")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = criteria_set_document(normalized, extra=extra)
    path.write_text(
        yaml.safe_dump(
            doc, sort_keys=False, allow_unicode=True, default_flow_style=False
        ),
        encoding="utf-8",
    )
    return normalized


def criteria_for_evaluator(criteria_set: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"id": str(c["id"]), "description": str(c["description"])}
        for c in criteria_set.get("criteria", [])
        if c.get("description")
    ]


def _load_yaml_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Criteria set file must contain a YAML mapping: {path}")
    return data
