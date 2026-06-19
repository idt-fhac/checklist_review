"""Unified criteria schema."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

CriteriaInput = Union[Dict[str, Any], Path]


def normalize_criterion(raw: Any, index: int) -> Dict[str, Any]:
    if isinstance(raw, str):
        return {"id": f"req-{index + 1}", "description": raw, "scoring_type": "checklist"}
    if not isinstance(raw, dict):
        return {"id": f"req-{index + 1}", "description": str(raw), "scoring_type": "checklist"}

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


def load_criteria_set(data: CriteriaInput, *, name: Optional[str] = None) -> Dict[str, Any]:
    if isinstance(data, Path):
        import json
        with data.open(encoding="utf-8") as fh:
            payload = json.load(fh)
        name = name or payload.get("name") or data.stem
    elif isinstance(data, dict):
        payload = data
        name = name or payload.get("name")
    else:
        raise ValueError("Criteria set must be a dict or file path")

    raw_items = payload.get("criteria")
    if not isinstance(raw_items, list):
        raise ValueError("Criteria set must contain a 'criteria' array")

    criteria = [normalize_criterion(item, i) for i, item in enumerate(raw_items)]
    criteria = [c for c in criteria if c.get("description")]

    return {
        "name": name or "criteria_set",
        "created_at": payload.get("created_at") or datetime.utcnow().isoformat(),
        "criteria": criteria,
    }


def criteria_for_evaluator(criteria_set: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"id": str(c["id"]), "description": str(c["description"])}
        for c in criteria_set.get("criteria", [])
        if c.get("description")
    ]
