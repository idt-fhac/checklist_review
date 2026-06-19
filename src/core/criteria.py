"""Unified criteria schema with backward compatibility for legacy checklists."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

CriteriaInput = Union[Dict[str, Any], List[Any], str, Path]


def _slug(value: str) -> str:
    return value.strip().replace(" ", "_").lower() or "criterion"


def normalize_criterion(raw: Any, index: int) -> Dict[str, Any]:
    """Normalize a single criterion to the unified schema."""
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

    description = (
        raw.get("description")
        or raw.get("text")
        or raw.get("question")
        or raw.get("content")
        or ""
    )
    criterion_id = raw.get("id") or raw.get("question_id") or f"req-{index + 1}"
    normalized: Dict[str, Any] = {
        "id": str(criterion_id),
        "description": str(description),
    }
    if raw.get("category"):
        normalized["category"] = raw["category"]
    if raw.get("weight") is not None:
        normalized["weight"] = raw["weight"]
    if raw.get("scoring_type"):
        normalized["scoring_type"] = raw["scoring_type"]
    elif raw.get("type"):
        normalized["scoring_type"] = raw["type"]
    else:
        normalized["scoring_type"] = "checklist"
    if raw.get("mandatory") is not None:
        normalized["mandatory"] = raw["mandatory"]
    if raw.get("source_ref"):
        normalized["source_ref"] = raw["source_ref"]
    return normalized


def extract_criteria_list(data: CriteriaInput) -> List[Any]:
    """Extract raw criteria items from various legacy checklist shapes."""
    if isinstance(data, Path):
        import json

        with data.open(encoding="utf-8") as fh:
            data = json.load(fh)
    if isinstance(data, str):
        import json

        data = json.loads(data)
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []

    for key in ("criteria", "questions", "content", "items"):
        if key in data and isinstance(data[key], list):
            return data[key]
    return []


def load_criteria_set(data: CriteriaInput, *, name: Optional[str] = None) -> Dict[str, Any]:
    """
    Load and normalize a criteria set from JSON data or file path.

    Accepts legacy checklist keys (questions, content, items) and emits the
    unified ``criteria`` list while preserving backward-compatible aliases.
    """
    if isinstance(data, Path):
        import json

        path = data
        with path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
        name = name or payload.get("name") or path.stem
        raw_items = extract_criteria_list(payload)
        metadata = {k: v for k, v in payload.items() if k not in ("questions", "content", "items", "criteria")}
    else:
        if isinstance(data, dict):
            payload = data
            raw_items = extract_criteria_list(payload)
            metadata = {k: v for k, v in payload.items() if k not in ("questions", "content", "items", "criteria")}
            name = name or payload.get("name")
        else:
            raw_items = extract_criteria_list(data)
            metadata = {}
    criteria = [normalize_criterion(item, i) for i, item in enumerate(raw_items)]
    criteria = [c for c in criteria if c.get("description")]

    result: Dict[str, Any] = {
        "name": name or "criteria_set",
        "created_at": metadata.get("created_at") or datetime.utcnow().isoformat(),
        "criteria": criteria,
        # Backward-compatible aliases for existing components
        "questions": [
            {"id": c["id"], "text": c["description"]} for c in criteria
        ],
    }
    result.update({k: v for k, v in metadata.items() if k not in result})
    return result


def criteria_for_reviewer(criteria_set: Dict[str, Any]) -> List[Dict[str, str]]:
    """Format criteria for question_reviewer / criterion_evaluator components."""
    questions = criteria_set.get("questions")
    if isinstance(questions, list) and questions:
        formatted: List[Dict[str, str]] = []
        for item in questions:
            if isinstance(item, dict):
                formatted.append(
                    {
                        "id": str(item.get("id", "")),
                        "text": str(item.get("text") or item.get("description") or ""),
                    }
                )
            else:
                formatted.append({"id": "", "text": str(item)})
        return [q for q in formatted if q.get("text")]

    criteria = criteria_set.get("criteria") or []
    return [
        {"id": str(c.get("id", "")), "text": str(c.get("description", ""))}
        for c in criteria
        if c.get("description")
    ]
