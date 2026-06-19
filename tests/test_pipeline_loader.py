from __future__ import annotations

from src.review_workflow.engine.pipeline_loader import build_review_process_definition


def test_tender_full_uses_multi_persona():
    definition = build_review_process_definition("tender_full")
    evaluation = definition["evaluation"]
    assert evaluation["mode"] == "multi_persona"
    persona_ids = [p["id"] for p in evaluation["personas"]]
    assert persona_ids == ["critic", "expert", "compliance"]
    assert evaluation["merge_strategy"] == "weighted"


def test_scientific_checklist_stays_single_persona():
    definition = build_review_process_definition("scientific_checklist")
    assert definition["evaluation"]["mode"] == "single"
    assert definition["evaluation"]["personas"] == []


def test_process_definition_includes_core_stages():
    definition = build_review_process_definition("tender_full")
    assert definition["document_loader"]
    assert definition["criteria_extractor"]
    assert definition["section_mapper"]
    assert definition["criterion_evaluator"]
    assert definition["feedback_synthesizer"]
    assert definition["post_processors"]
