"""Merge extracted criteria with evaluation results for report overviews."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

WEIGHT_PATTERN = re.compile(
    r"(?:Gewichtung|weight(?:ing)?)\s*[:.]?\s*(\d+(?:[.,]\d+)?)\s*%",
    re.IGNORECASE,
)


def resolve_criterion_weight(criterion: Dict[str, Any]) -> Optional[float]:
    """Return criterion weight as a percentage (e.g. 15.0), if known."""
    raw_weight = criterion.get("weight")
    if raw_weight is not None:
        try:
            value = float(str(raw_weight).replace(",", ".").rstrip("%").strip())
            if value <= 1:
                return round(value * 100, 2)
            return round(value, 2)
        except (TypeError, ValueError):
            pass

    description = str(criterion.get("description") or "")
    match = WEIGHT_PATTERN.search(description)
    if match:
        return round(float(match.group(1).replace(",", ".")), 2)
    return None


def build_criteria_overview(
    criteria_doc: Optional[Dict[str, Any]],
    evaluation_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    criteria_by_id: Dict[str, Dict[str, Any]] = {}
    if criteria_doc:
        for item in criteria_doc.get("criteria") or []:
            if isinstance(item, dict) and item.get("id"):
                criteria_by_id[str(item["id"])] = item

    rows: List[Dict[str, Any]] = []
    met_count = 0
    not_met_count = 0
    other_count = 0
    weighted_total = 0.0
    weighted_earned = 0.0
    disagreement_count = 0

    for evaluation in evaluation_items:
        if not isinstance(evaluation, dict):
            continue
        criterion_id = str(evaluation.get("criterion_id") or "")
        criterion = criteria_by_id.get(criterion_id, {})
        weight = resolve_criterion_weight(criterion)
        answer = evaluation.get("answer")
        if answer is True:
            met_count += 1
        elif answer is False:
            not_met_count += 1
        else:
            other_count += 1
        if evaluation.get("disagreement"):
            disagreement_count += 1
        if weight is not None:
            weighted_total += weight
            if answer is True:
                weighted_earned += weight

        rows.append(
            {
                "criterion_id": criterion_id or None,
                "description": evaluation.get("criterion_text")
                or criterion.get("description")
                or criterion_id
                or "Criterion",
                "source_ref": criterion.get("source_ref"),
                "weight": weight,
                "weight_label": f"{weight:g}%" if weight is not None else None,
                "scoring_type": criterion.get("scoring_type"),
                "mandatory": criterion.get("mandatory"),
                "answer": answer,
                "disagreement": bool(evaluation.get("disagreement")),
            }
        )

    weighted_score_percent = None
    if weighted_total > 0:
        weighted_score_percent = round((weighted_earned / weighted_total) * 100, 1)

    return {
        "rows": rows,
        "summary": {
            "total": len(rows),
            "met": met_count,
            "not_met": not_met_count,
            "other": other_count,
            "disagreements": disagreement_count,
            "weighted_total": round(weighted_total, 2) if weighted_total else None,
            "weighted_earned": round(weighted_earned, 2) if weighted_total else None,
            "weighted_score_percent": weighted_score_percent,
        },
    }
