from __future__ import annotations

from src.core.criteria_overview import build_criteria_overview, resolve_criterion_weight


def test_resolve_weight_from_description():
    criterion = {
        "description": "Innovationshöhe ... (Gewichtung 15%).",
    }
    assert resolve_criterion_weight(criterion) == 15.0


def test_resolve_weight_from_field():
    criterion = {"description": "Test", "weight": 30}
    assert resolve_criterion_weight(criterion) == 30.0


def test_build_overview_computes_weighted_score():
    criteria_doc = {
        "criteria": [
            {"id": "a", "description": "A (Gewichtung 60%).", "source_ref": "1"},
            {"id": "b", "description": "B (Gewichtung 40%).", "source_ref": "2"},
        ]
    }
    evaluations = [
        {"criterion_id": "a", "criterion_text": "A", "answer": True},
        {
            "criterion_id": "b",
            "criterion_text": "B",
            "answer": False,
            "disagreement": True,
        },
    ]

    overview = build_criteria_overview(criteria_doc, evaluations)
    assert overview["summary"]["total"] == 2
    assert overview["summary"]["weighted_total"] == 100.0
    assert overview["summary"]["weighted_earned"] == 60.0
    assert overview["summary"]["weighted_score_percent"] == 60.0
    assert overview["rows"][0]["weight_label"] == "60%"
    assert overview["rows"][1]["disagreement"] is True
