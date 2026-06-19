"""Merge per-persona criterion evaluations into a single merged result."""

from __future__ import annotations

from typing import Any, Dict, List


def _persona_answer(result: Dict[str, Any]) -> bool:
    answer = result.get("answer")
    if isinstance(answer, bool):
        return answer
    if isinstance(answer, str):
        normalized = answer.strip().lower()
        if normalized in {"true", "yes", "met", "pass", "passed"}:
            return True
        if normalized in {"false", "no", "not met", "fail", "failed"}:
            return False
    return bool(answer)


def merge_criterion_results(
    persona_results: Dict[str, Dict[str, Any]],
    personas: List[Dict[str, Any]],
    *,
    merge_strategy: str = "weighted",
) -> Dict[str, Any]:
    if not persona_results:
        raise ValueError("persona_results is empty")

    sample = next(iter(persona_results.values()))
    criterion_id = sample.get("criterion_id")
    criterion_text = sample.get("criterion_text") or sample.get("description") or ""

    persona_scores: Dict[str, Any] = {}
    answers: Dict[str, bool] = {}
    weights: Dict[str, float] = {}

    for persona in personas:
        persona_id = persona["id"]
        weights[persona_id] = float(persona.get("weight", 1.0))
        result = persona_results.get(persona_id) or {}
        answer = _persona_answer(result)
        answers[persona_id] = answer
        persona_scores[persona_id] = {
            "persona_id": persona_id,
            "label": persona.get("label") or persona_id,
            "weight": weights[persona_id],
            "answer": answer,
            "supporting_texts": result.get("supporting_texts") or [],
            "reasoning": result.get("reasoning") or result.get("explanation") or "",
        }

    unique_answers = set(answers.values())
    disagreement = len(unique_answers) > 1

    if merge_strategy == "strict":
        merged_answer = all(answers.values())
    elif merge_strategy == "any_true":
        merged_answer = any(answers.values())
    else:
        total_weight = sum(weights.get(pid, 1.0) for pid in answers) or 1.0
        weighted_score = sum(
            weights.get(pid, 1.0) * (1.0 if answers[pid] else 0.0) for pid in answers
        ) / total_weight
        merged_answer = weighted_score >= 0.5

    supporting_texts: List[Dict[str, Any]] = []
    for persona_id, score in persona_scores.items():
        for item in score.get("supporting_texts") or []:
            enriched = dict(item)
            enriched["persona_id"] = persona_id
            enriched["persona_label"] = score.get("label") or persona_id
            supporting_texts.append(enriched)

    dissenting = [pid for pid, answer in answers.items() if answer != merged_answer]
    reasoning_parts = []
    for persona_id, score in persona_scores.items():
        text = score.get("reasoning") or ""
        if text:
            label = score.get("label") or persona_id
            reasoning_parts.append(f"[{label}] {text}")
    if disagreement and dissenting:
        reasoning_parts.append(
            f"Persona disagreement: dissenting viewpoints from {', '.join(dissenting)}."
        )

    return {
        "criterion_id": criterion_id,
        "criterion_text": criterion_text,
        "answer": merged_answer,
        "supporting_texts": supporting_texts,
        "reasoning": " ".join(reasoning_parts).strip(),
        "persona_scores": persona_scores,
        "disagreement": disagreement,
        "merge_strategy": merge_strategy,
    }


def normalize_persona_weights(personas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    total = sum(float(p.get("weight", 1.0)) for p in personas) or 1.0
    normalized = []
    for persona in personas:
        item = dict(persona)
        item["weight"] = float(persona.get("weight", 1.0)) / total
        normalized.append(item)
    return normalized
