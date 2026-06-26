import re
from typing import Any, Dict, List, Optional

from src.review_workflow.components.evaluators.criterion_evaluator.helpers import (
    clean_text_for_encoding,
)


def build_prompt_with_pages(
    criterion_text: str,
    paper_content: str,
    artifact_pages: Optional[List[Dict[str, Any]]],
) -> str:
    criterion_text = clean_text_for_encoding(criterion_text)
    if isinstance(paper_content, str):
        paper_content = clean_text_for_encoding(paper_content)

    # prompt = f"Answer this question based on the paper content: {criterion_text}\n\n"
    prompt = f"Question: {criterion_text}\n\n"
    rag_separator = "=" * 80

    if rag_separator in paper_content:
        prompt += f"Paper Content (with page numbers):\n{rag_separator}\n"
        separator_pattern = r"\n\n" + re.escape(rag_separator) + r"\n\n"
        chunks = re.split(separator_pattern, paper_content)

        for chunk in chunks:
            if not chunk.strip():
                continue

            page_match = re.search(
                r"\n\n?PAGE NUMBER\s+(\d+|Unknown)\s*$",
                chunk,
                re.IGNORECASE | re.MULTILINE,
            )
            if page_match:
                page_num_str = page_match.group(1)
                content = re.sub(
                    r"\n\n?PAGE NUMBER\s+\d+|Unknown\s*$",
                    "",
                    chunk,
                    flags=re.IGNORECASE | re.MULTILINE,
                ).strip()
                page_num = page_num_str if page_num_str != "Unknown" else "?"
            else:
                page_match_anywhere = re.search(
                    r"PAGE NUMBER\s+(\d+|Unknown)", chunk, re.IGNORECASE
                )
                if page_match_anywhere:
                    page_num_str = page_match_anywhere.group(1)
                    page_num = page_num_str if page_num_str != "Unknown" else "?"
                    content = re.sub(
                        r"\n\n?PAGE NUMBER\s+\d+|Unknown\s*",
                        "",
                        chunk,
                        flags=re.IGNORECASE,
                    ).strip()
                else:
                    page_num = "?"
                    content = chunk.strip()

            if content:
                prompt += f"\n\n\n-------------------------> PAGE {page_num} ---\n\n{content}\n\n"

        prompt += f"{rag_separator}\n"
    elif artifact_pages:
        prompt += f"Paper Content (with page numbers):\n{rag_separator}\n"
        for page_info in artifact_pages:
            page_num = page_info.get("page_number", "?")
            page_text = page_info.get("content", page_info.get("text", ""))
            page_text = clean_text_for_encoding(str(page_text))
            prompt += f"\n\n\n------------------------->  PAGE {page_num} ---\n\n{page_text}\n\n"
        prompt += f"{rag_separator}\n"
    else:
        prompt += f"Paper Content:\n{paper_content}\n"

    prompt = clean_text_for_encoding(prompt)

    return prompt


def build_batch_prompt(
    questions: List[Dict[str, Any]],
    paper_content: str,
    artifact_pages: Optional[List[Dict[str, Any]]],
) -> str:
    prompt = "You need to answer multiple questions about the paper. Here are the questions:\n\n"

    for idx, question in enumerate(questions, 1):
        criterion_id = question.get("id", f"q{idx}")
        criterion_text = clean_text_for_encoding(question.get("text", ""))
        prompt += f"Question {idx} (ID: {criterion_id}): {criterion_text}\n\n"

    prompt += "CRITICAL: When providing your answers, you MUST use the exact criterion_id from above for each answer. "
    prompt += "The criterion_id must match exactly (e.g., if the question ID is 'q1', use 'q1' in your answer, not 'Question 1' or '1').\n\n"

    prompt += "\n" + "=" * 80 + "\n"
    rag_separator = "=" * 80

    if rag_separator in paper_content:
        prompt += f"Paper Content (with page numbers):\n{rag_separator}\n"
        separator_pattern = r"\n\n" + re.escape(rag_separator) + r"\n\n"
        chunks = re.split(separator_pattern, paper_content)

        for chunk in chunks:
            if not chunk.strip():
                continue

            page_match = re.search(
                r"\n\n?PAGE NUMBER\s+(\d+|Unknown)\s*$",
                chunk,
                re.IGNORECASE | re.MULTILINE,
            )
            if page_match:
                page_num_str = page_match.group(1)
                content = re.sub(
                    r"\n\n?PAGE NUMBER\s+\d+|Unknown\s*$",
                    "",
                    chunk,
                    flags=re.IGNORECASE | re.MULTILINE,
                ).strip()
                page_num = page_num_str if page_num_str != "Unknown" else "?"
            else:
                page_match_anywhere = re.search(
                    r"PAGE NUMBER\s+(\d+|Unknown)", chunk, re.IGNORECASE
                )
                if page_match_anywhere:
                    page_num_str = page_match_anywhere.group(1)
                    page_num = page_num_str if page_num_str != "Unknown" else "?"
                    content = re.sub(
                        r"\n\n?PAGE NUMBER\s+\d+|Unknown\s*",
                        "",
                        chunk,
                        flags=re.IGNORECASE,
                    ).strip()
                else:
                    page_num = "?"
                    content = chunk.strip()

            if content:
                prompt += f"\n--- PAGE {page_num} ---\n{content}\n"

        prompt += f"{rag_separator}\n"
    elif artifact_pages:
        prompt += f"Paper Content (with page numbers):\n{rag_separator}\n"
        for page_info in artifact_pages:
            page_num = page_info.get("page_number", "?")
            page_text = page_info.get("content", page_info.get("text", ""))
            page_text = clean_text_for_encoding(str(page_text))
            prompt += f"\n--- PAGE {page_num} ---\n{page_text}\n"
        prompt += f"{rag_separator}\n"
    else:
        prompt += f"Paper Content:\n{paper_content}\n"

    prompt = clean_text_for_encoding(prompt)

    prompt += "\nIMPORTANT: You MUST provide answers for ALL questions listed above. "
    prompt += "Each answer MUST include:\n"
    prompt += "1. The criterion_id that matches one of the questions above\n"
    prompt += "2. An answer (True/False)\n"
    prompt += "3. Supporting text items with page_number (1-indexed, or -1 for analysis-only), verbatim text_crop, and short_explanation\n"
    prompt += "4. At least one supporting text should reference a specific page when possible\n"
    prompt += "5. You must answer ALL questions - do not skip any questions\n"

    return prompt
