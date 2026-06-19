"""LLM-based criteria extraction from source documents."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

try:
    import pymupdf
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

from strands import Agent

from src.core.pdf_processing import load_model_from_provider, PDFProcessingError


class ExtractedCriterion(BaseModel):
    id: str = Field(description="Stable requirement id, e.g. req-3.2.1")
    description: str = Field(description="Requirement text")
    scoring_type: str = Field(default="pass_fail", description="checklist | pass_fail | scale")
    source_ref: Optional[str] = Field(default=None, description="Section or clause reference")


class ExtractedCriteriaSet(BaseModel):
    criteria: List[ExtractedCriterion] = Field(description="All extracted criteria")


def read_document_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        if not PYMUPDF_AVAILABLE:
            raise PDFProcessingError("pymupdf is required to extract text from PDF sources")
        doc = pymupdf.open(str(path))
        pages = [doc[i].get_text("text", sort=True) for i in range(doc.page_count)]
        doc.close()
        return "\n\n".join(pages)
    if suffix in (".md", ".txt"):
        return path.read_text(encoding="utf-8")
    if suffix in (".yaml", ".yml"):
        return path.read_text(encoding="utf-8")
    raise PDFProcessingError(f"Unsupported criteria source format: {path.suffix}")


def extract_criteria_from_text(
    document_text: str,
    provider_config: Dict[str, Any],
    *,
    system_prompt: Optional[str] = None,
    scoring_default: str = "pass_fail",
) -> List[Dict[str, Any]]:
    if not document_text.strip():
        raise PDFProcessingError("Criteria source document is empty")

    system_prompt = system_prompt or (
        "You extract structured evaluation criteria from requirement documents (RFPs, rubrics, checklists). "
        "Return atomic, testable criteria with stable ids and clause references when visible."
    )
    user_prompt = f"""Extract all evaluation criteria from this document.

Use scoring_type "{scoring_default}" unless the document specifies another scheme.
Include source_ref when a section/clause number is visible.

Document:
{document_text[:120000]}
"""

    model = load_model_from_provider(provider_config)
    agent = Agent(model=model, system_prompt=system_prompt)

    try:
        response = agent(user_prompt, structured_output_model=ExtractedCriteriaSet)
        items = response.structured_output.model_dump()["criteria"]
    except Exception as exc:
        if "structured" not in str(exc).lower():
            raise
        response = agent(user_prompt)
        text = getattr(response, "text", None) or getattr(response, "content", None) or str(response)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise PDFProcessingError("Failed to parse extracted criteria") from exc
        items = json.loads(match.group(0)).get("criteria", [])

    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(items):
        if isinstance(item, dict):
            normalized.append(
                {
                    "id": str(item.get("id") or f"req-{index + 1}"),
                    "description": str(item.get("description") or item.get("text") or ""),
                    "scoring_type": item.get("scoring_type") or scoring_default,
                    "source_ref": item.get("source_ref"),
                }
            )
    return [c for c in normalized if c.get("description")]
