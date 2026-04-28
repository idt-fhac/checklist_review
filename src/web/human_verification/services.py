from __future__ import annotations

from typing import Any, Dict, List, Optional


def _normalize_answers_list(data: Any) -> List[Dict[str, Any]]:
    """Normalize loaded JSON to a list of answer dicts (e.g. from answers.json)."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "answers" in data:
        return data["answers"]
    if isinstance(data, dict) and "entries" in data:
        return data["entries"]
    return []


def compare_ground_truth_to_generated(
    ground_truth_data: Any,
    generated_data: Any,
) -> Dict[str, Dict[str, Any]]:
    """
    Compare ground-truth answers (human) with generated answers (review process).
    Returns verifications dict: question_id -> { "is_correct": bool, "comment": "" }.
    Match = both true or both false -> is_correct True; otherwise False.
    """
    gt_list = _normalize_answers_list(ground_truth_data)
    gen_list = _normalize_answers_list(generated_data)
    gt_by_id = {str(item.get("question_id", "")): item for item in gt_list if item.get("question_id") is not None}
    verifications = {}
    for gen_item in gen_list:
        qid = str(gen_item.get("question_id", ""))
        if not qid:
            continue
        gt_item = gt_by_id.get(qid)
        gen_answer = gen_item.get("answer")
        if gt_item is None:
            verifications[qid] = {"is_correct": None, "comment": "No ground-truth for this question"}
            continue
        gt_answer = gt_item.get("answer")
        is_correct = (gt_answer is gen_answer) or (bool(gt_answer) == bool(gen_answer))
        verifications[qid] = {"is_correct": is_correct, "comment": ""}
    return verifications


def prepare_review_view(answers: List[Dict[str, Any]], verification: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    if not answers:
        return []
        
    verification_map = {}
    if verification and "verifications" in verification:
        verification_map = verification["verifications"]
        
    return [
        {
            "question_id": ans.get("question_id"),
            "question_text": ans.get("question_text"),
            "automated_answer": ans.get("answer"),
            "supporting_texts": ans.get("supporting_texts", []),
            "human_is_correct": verification_map.get(ans.get("question_id"), {}).get("is_correct"),
            "human_comment": verification_map.get(ans.get("question_id"), {}).get("comment", "")
        }
        for ans in answers
    ]


def capture_verification_updates(form_data: Dict[str, str]) -> Dict[str, Any]:
    verifications = {}
    
    for key, value in form_data.items():
        if key.startswith("verify_status::"):
            _, question_id = key.split("::", 1)
            comment = form_data.get(f"verify_comment::{question_id}", "")
            
            is_correct = None
            if value == "correct":
                is_correct = True
            elif value == "incorrect":
                is_correct = False
            
            verifications[question_id] = {
                "is_correct": is_correct,
                "comment": comment
            }
            
    return {"verifications": verifications}
