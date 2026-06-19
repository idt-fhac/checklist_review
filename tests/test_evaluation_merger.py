from __future__ import annotations

import pytest

from src.review_workflow.engine.evaluation_merger import (
    merge_criterion_results,
    normalize_persona_weights,
)


PERSONAS = [
    {"id": "critic", "label": "Critic", "weight": 0.35},
    {"id": "expert", "label": "Expert", "weight": 0.35},
    {"id": "compliance", "label": "Compliance", "weight": 0.30},
]


def _result(persona_id: str, answer: bool, reasoning: str = "") -> dict:
    return {
        "criterion_id": "req-1",
        "criterion_text": "Provide case studies",
        "answer": answer,
        "reasoning": reasoning or f"{persona_id} view",
    }


class TestMergeCriterionResults:
    def test_weighted_merge_majority_true(self):
        merged = merge_criterion_results(
            {
                "critic": _result("critic", False),
                "expert": _result("expert", True),
                "compliance": _result("compliance", True),
            },
            PERSONAS,
            merge_strategy="weighted",
        )
        assert merged["answer"] is True
        assert merged["disagreement"] is True
        assert set(merged["persona_scores"]) == {"critic", "expert", "compliance"}

    def test_strict_merge_requires_unanimity(self):
        merged = merge_criterion_results(
            {
                "critic": _result("critic", False),
                "expert": _result("expert", True),
                "compliance": _result("compliance", True),
            },
            PERSONAS,
            merge_strategy="strict",
        )
        assert merged["answer"] is False

    def test_any_true_merge(self):
        merged = merge_criterion_results(
            {
                "critic": _result("critic", False),
                "expert": _result("expert", False),
                "compliance": _result("compliance", True),
            },
            PERSONAS,
            merge_strategy="any_true",
        )
        assert merged["answer"] is True

    def test_string_answers_normalized(self):
        merged = merge_criterion_results(
            {
                "critic": {"criterion_id": "r1", "criterion_text": "X", "answer": "met"},
                "expert": {"criterion_id": "r1", "criterion_text": "X", "answer": "not met"},
            },
            PERSONAS[:2],
            merge_strategy="weighted",
        )
        assert merged["persona_scores"]["critic"]["answer"] is True
        assert merged["persona_scores"]["expert"]["answer"] is False

    def test_empty_persona_results_raises(self):
        with pytest.raises(ValueError, match="empty"):
            merge_criterion_results({}, PERSONAS)


class TestNormalizePersonaWeights:
    def test_weights_sum_to_one(self):
        normalized = normalize_persona_weights(PERSONAS)
        assert sum(p["weight"] for p in normalized) == pytest.approx(1.0)
