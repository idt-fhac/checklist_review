import json
import re
from typing import Any, Dict, List, Optional

from src.review_workflow.components.evaluators.criterion_evaluator.helpers import (
    clean_text_for_encoding,
)
from src.review_workflow.engine.token_usage import add as token_usage_add


def extract_response_text(response) -> str:
    if hasattr(response, "text"):
        return response.text
    if hasattr(response, "content"):
        return response.content
    if hasattr(response, "message") and hasattr(response.message, "content"):
        return response.message.content
    if isinstance(response, str):
        return response
    return str(response)


def fix_json_common_issues(json_str: str) -> str:
    json_str = re.sub(r",(\s*[}\]])", r"\1", json_str)
    json_str = re.sub(r"//.*?$", "", json_str, flags=re.MULTILINE)
    json_str = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)
    return json_str


def parse_json_from_text(response_text: str) -> Optional[Dict[str, Any]]:
    json_candidates = []
    brace_depth = 0
    start_idx = -1

    for i, char in enumerate(response_text):
        if char == "{":
            if brace_depth == 0:
                start_idx = i
            brace_depth += 1
        elif char == "}":
            brace_depth -= 1
            if brace_depth == 0 and start_idx >= 0:
                candidate = response_text[start_idx : i + 1]
                if '"answer"' in candidate.lower():
                    json_candidates.append(candidate)
                start_idx = -1

    for candidate in json_candidates:
        try:
            fixed = fix_json_common_issues(candidate)
            return json.loads(fixed)
        except json.JSONDecodeError:
            continue

    json_patterns = [
        r'\{[^{}]*"answer"[^{}]*(?:\{[^{}]*"supporting_texts"[^{}]*\[.*?\][^{}]*\}[^{}]*)*\}',
        r'\{.*?"answer".*?:.*?(?:true|false).*?"supporting_texts".*?:.*?\[.*?\].*?\}',
    ]
    for pattern in json_patterns:
        json_match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)
        if json_match:
            try:
                fixed = fix_json_common_issues(json_match.group(0))
                return json.loads(fixed)
            except json.JSONDecodeError:
                continue
    return None


def format_parsed_result(parsed: Dict[str, Any]) -> Dict[str, Any]:
    result = {"answer": bool(parsed.get("answer", False)), "supporting_texts": []}
    supporting_texts = parsed.get("supporting_texts", [])
    for st in supporting_texts:
        if isinstance(st, dict):
            result["supporting_texts"].append(
                {
                    "page_number": int(st.get("page_number", -1)),
                    "text_crop": str(st.get("text_crop", "")),
                    "short_explanation": str(
                        st.get("short_explanation", "No explanation provided")
                    ),
                }
            )
    if not result["supporting_texts"]:
        result["supporting_texts"] = [
            {
                "page_number": -1,
                "text_crop": "No supporting text extracted from fallback parsing",
                "short_explanation": "Fallback parsing did not extract any supporting text",
            }
        ]
    return result


def extract_from_text_fallback(response_text: str) -> Dict[str, Any]:
    answer_match = re.search(
        r'"answer"\s*:\s*(true|false)', response_text, re.IGNORECASE
    )
    answer = answer_match.group(1).lower() == "true" if answer_match else False

    supporting_texts = []
    st_match = re.search(
        r'"supporting_texts"\s*:\s*\[(.*?)\]', response_text, re.DOTALL | re.IGNORECASE
    )

    if st_match:
        st_content = st_match.group(1)
        st_objects = re.finditer(
            r'\{[^{}]*(?:"page_number"[^{}]*"text_crop"|"text_crop"[^{}]*"page_number")[^{}]*\}',
            st_content,
            re.DOTALL,
        )
        for obj_match in st_objects:
            try:
                fixed = fix_json_common_issues(obj_match.group(0))
                st_obj = json.loads(fixed)
                supporting_texts.append(
                    {
                        "page_number": int(st_obj.get("page_number", -1)),
                        "text_crop": str(st_obj.get("text_crop", "")),
                        "short_explanation": str(
                            st_obj.get(
                                "short_explanation", "Extracted from fallback parsing"
                            )
                        ),
                    }
                )
            except (json.JSONDecodeError, ValueError, KeyError):
                continue

    if not supporting_texts:
        page_matches = re.finditer(r"page\s+(\d+)", response_text, re.IGNORECASE)
        for match in page_matches:
            page_num = int(match.group(1))
            start = max(0, match.start() - 100)
            end = min(len(response_text), match.end() + 200)
            supporting_texts.append(
                {
                    "page_number": page_num,
                    "text_crop": response_text[start:end].strip(),
                    "short_explanation": "Extracted from text fallback parsing",
                }
            )

    if not supporting_texts:
        supporting_texts = [
            {
                "page_number": -1,
                "text_crop": response_text[:500],
                "short_explanation": "Full response text used as supporting text",
            }
        ]

    return {"answer": answer, "supporting_texts": supporting_texts}


def extract_from_text_only(
    agent,
    prompt: str,
    provider_config: Dict[str, Any],
    token_usage_accumulator: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    simple_prompt = (
        prompt
        + "\n\nPlease provide your answer (True or False) and cite supporting text from the paper with page numbers."
    )
    simple_prompt = clean_text_for_encoding(simple_prompt)
    response = agent(simple_prompt)
    if token_usage_accumulator is not None:
        token_usage_add(token_usage_accumulator, response, agent)
    response_text = extract_response_text(response)

    answer = False
    answer_patterns = [
        r"\b(answer|result|conclusion)[\s:]+(true|yes|correct|affirmative)",
        r"\b(true|yes|correct)\b",
        r"answer[\s:]+true",
    ]
    for pattern in answer_patterns:
        if re.search(pattern, response_text, re.IGNORECASE):
            answer = True
            break

    if re.search(r"\b(false|no|incorrect|negative)\b", response_text, re.IGNORECASE):
        answer = False

    supporting_texts = []
    page_patterns = [
        r"page\s+(\d+)",
        r"p\.\s*(\d+)",
        r"pg\.\s*(\d+)",
        r"on\s+page\s+(\d+)",
    ]

    for pattern in page_patterns:
        for match in re.finditer(pattern, response_text, re.IGNORECASE):
            page_num = int(match.group(1))
            start = max(0, match.start() - 200)
            end = min(len(response_text), match.end() + 200)
            supporting_texts.append(
                {
                    "page_number": page_num,
                    "text_crop": re.sub(r"\s+", " ", response_text[start:end].strip()),
                    "short_explanation": "Extracted from text-only parsing",
                }
            )

    if not supporting_texts:
        sentences = re.split(r"[.!?]+", response_text)
        relevant_sentences = [s.strip() for s in sentences if len(s.strip()) > 20][:3]
        supporting_texts = [
            {
                "page_number": -1,
                "text_crop": " ".join(relevant_sentences)
                if relevant_sentences
                else response_text[:500],
                "short_explanation": "Analysis extracted from full response",
            }
        ]

    return {"answer": answer, "supporting_texts": supporting_texts}


def fallback_structured_output(
    agent,
    prompt: str,
    provider_config: Dict[str, Any],
    token_usage_accumulator: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    json_prompt = (
        prompt
        + "\n\nIMPORTANT: Respond with ONLY a valid JSON object in this exact format (no other text):\n"
        + '{"answer": true, "supporting_texts": [{"page_number": 1, "text_crop": "exact text from paper", "short_explanation": "why this supports the answer"}]}'
    )
    json_prompt = clean_text_for_encoding(json_prompt)
    response = agent(json_prompt)
    if token_usage_accumulator is not None:
        token_usage_add(token_usage_accumulator, response, agent)
    response_text = extract_response_text(response)

    parsed = parse_json_from_text(response_text)
    if parsed:
        return format_parsed_result(parsed)

    return extract_from_text_fallback(response_text)


def parse_batch_json_from_text(
    response_text: str, questions: List[Dict[str, Any]]
) -> Optional[List[Dict[str, Any]]]:
    try:
        json_data = json.loads(response_text)
        if isinstance(json_data, dict) and "answers" in json_data:
            answers = json_data["answers"]
            if isinstance(answers, list):
                result_list = []
                for answer in answers:
                    if isinstance(answer, dict):
                        result_list.append(
                            {
                                "criterion_id": str(answer.get("criterion_id", "")),
                                "answer": bool(answer.get("answer", False)),
                                "supporting_texts": answer.get("supporting_texts", []),
                            }
                        )
                return result_list
    except json.JSONDecodeError:
        pass

    json_patterns = [
        r'\{"answers"\s*:\s*\[.*?\]\}',
        r'\[.*?"criterion_id".*?\]',
    ]

    for pattern in json_patterns:
        json_match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)
        if json_match:
            try:
                fixed = fix_json_common_issues(json_match.group(0))
                json_data = json.loads(fixed)
                if isinstance(json_data, dict) and "answers" in json_data:
                    answers = json_data["answers"]
                    if isinstance(answers, list):
                        result_list = []
                        for answer in answers:
                            if isinstance(answer, dict):
                                result_list.append(
                                    {
                                        "criterion_id": str(
                                            answer.get("criterion_id", "")
                                        ),
                                        "answer": bool(answer.get("answer", False)),
                                        "supporting_texts": answer.get(
                                            "supporting_texts", []
                                        ),
                                    }
                                )
                        return result_list
            except (json.JSONDecodeError, ValueError):
                continue

    return None


def extract_batch_from_text_fallback(
    response_text: str, questions: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    result_list = []
    criterion_ids = {q.get("id"): q for q in questions}

    for criterion_id, criterion_data in criterion_ids.items():
        criterion_text = criterion_data.get("text", "")

        answer = False
        answer_patterns = [
            rf"question.*?{re.escape(criterion_id)}.*?(?:answer|result)[\s:]+(true|yes|correct)",
            rf"{re.escape(criterion_id)}.*?(?:answer|result)[\s:]+(true|yes|correct)",
            rf"question.*?{re.escape(criterion_text[:50])}.*?(?:answer|result)[\s:]+(true|yes|correct)",
        ]

        for pattern in answer_patterns:
            if re.search(pattern, response_text, re.IGNORECASE | re.DOTALL):
                answer = True
                break

        if re.search(
            rf"{re.escape(criterion_id)}.*?(?:answer|result)[\s:]+(false|no|incorrect)",
            response_text,
            re.IGNORECASE,
        ):
            answer = False

        supporting_texts = []
        page_patterns = [r"page\s+(\d+)", r"p\.\s*(\d+)", r"pg\.\s*(\d+)"]

        for pattern in page_patterns:
            for match in re.finditer(pattern, response_text, re.IGNORECASE):
                page_num = int(match.group(1))
                start = max(0, match.start() - 200)
                end = min(len(response_text), match.end() + 200)
                supporting_texts.append(
                    {
                        "page_number": page_num,
                        "text_crop": response_text[start:end].strip(),
                        "short_explanation": "Extracted from batch text fallback",
                    }
                )

        if not supporting_texts:
            supporting_texts = [
                {
                    "page_number": -1,
                    "text_crop": response_text[:500],
                    "short_explanation": "Extracted from batch response",
                }
            ]

        result_list.append(
            {
                "criterion_id": criterion_id,
                "answer": answer,
                "supporting_texts": supporting_texts[:3],
            }
        )

    return result_list


def extract_batch_from_text_only(
    agent,
    prompt: str,
    provider_config: Dict[str, Any],
    questions: List[Dict[str, Any]],
    token_usage_accumulator: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    simple_prompt = (
        prompt
        + "\n\nPlease provide answers for all questions listed above. For each question, provide the criterion_id, answer (True/False), and cite supporting text with page numbers."
    )
    simple_prompt = clean_text_for_encoding(simple_prompt)
    response = agent(simple_prompt)
    if token_usage_accumulator is not None:
        token_usage_add(token_usage_accumulator, response, agent)
    response_text = extract_response_text(response)
    return extract_batch_from_text_fallback(response_text, questions)


def fallback_batch_structured_output(
    agent,
    prompt: str,
    provider_config: Dict[str, Any],
    questions: List[Dict[str, Any]],
    token_usage_accumulator: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    example_answers = []
    for q in questions:
        example_answers.append(
            {
                "criterion_id": q.get("id", ""),
                "answer": True,
                "supporting_texts": [
                    {
                        "page_number": 1,
                        "text_crop": "example text",
                        "short_explanation": "example",
                    }
                ],
            }
        )
    json_prompt = (
        prompt
        + "\n\nIMPORTANT: Respond with ONLY a valid JSON object in this exact format (no other text):\n"
        + json.dumps({"answers": example_answers}, indent=2)
    )
    json_prompt = clean_text_for_encoding(json_prompt)
    response = agent(json_prompt)
    if token_usage_accumulator is not None:
        token_usage_add(token_usage_accumulator, response, agent)
    response_text = extract_response_text(response)

    parsed = parse_batch_json_from_text(response_text, questions)
    if parsed:
        return parsed

    return extract_batch_from_text_fallback(response_text, questions)
