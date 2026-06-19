"""Map criteria to artifact sections using heading-based keyword matching."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.core.criteria import criteria_set_stem
from src.review_workflow.engine.base import BaseComponent
from src.review_workflow.engine.run_paths import artifact_run_dir

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def parse_markdown_sections(md_content: str) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    matches = list(HEADING_RE.finditer(md_content))
    if not matches:
        excerpt = md_content.strip()[:4000]
        if excerpt:
            sections.append({"heading": "Document", "level": 1, "content": excerpt})
        return sections

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(md_content)
        heading = match.group(2).strip()
        content = md_content[start:end].strip()
        sections.append(
            {
                "heading": heading,
                "level": len(match.group(1)),
                "content": content[:8000],
            }
        )
    return sections


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{4,}", text.lower())}


def match_criterion_to_sections(
    criterion: Dict[str, Any],
    sections: List[Dict[str, Any]],
    *,
    top_k: int = 2,
) -> Tuple[List[str], str]:
    description = criterion.get("description") or ""
    query_tokens = _tokenize(description)
    if not query_tokens:
        return [], ""

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for section in sections:
        heading_tokens = _tokenize(section.get("heading") or "")
        content_tokens = _tokenize(section.get("content") or "")
        overlap = len(query_tokens & (heading_tokens | content_tokens))
        if overlap:
            score = overlap + (2 * len(query_tokens & heading_tokens))
            scored.append((score, section))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [section for _, section in scored[:top_k]]
    if not selected and sections:
        selected = [sections[0]]

    headings = [section["heading"] for section in selected]
    excerpt = "\n\n".join(
        f"## {section['heading']}\n{section.get('content', '')[:3000]}"
        for section in selected
    )
    return headings, excerpt.strip()


def build_section_mapping(criteria: List[Dict[str, Any]], md_content: str) -> Dict[str, Any]:
    sections = parse_markdown_sections(md_content)
    mappings = []
    for criterion in criteria:
        criterion_id = str(criterion.get("id"))
        headings, excerpt = match_criterion_to_sections(criterion, sections)
        mappings.append(
            {
                "criterion_id": criterion_id,
                "headings": headings,
                "excerpt": excerpt,
            }
        )
    return {"schema_version": 1, "strategy": "heading_match", "mappings": mappings}


class SectionMapper(BaseComponent):
    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        collection_name = inputs["collection_name"]
        pipeline_name = inputs["pipeline_name"]
        artifact_name = inputs["artifact_name"]
        criteria_set_name = inputs["criteria_set_name"]
        collections_root = inputs["collections_root"]
        criteria = inputs.get("criteria") or []
        log_callback = inputs.get("log_callback")

        run_dir = artifact_run_dir(
            Path(collections_root),
            collection_name,
            pipeline_name,
            artifact_name,
            criteria_set_stem(criteria_set_name),
        )
        md_path = run_dir / "artifact_content.md"
        if not md_path.exists():
            raise FileNotFoundError(f"Artifact markdown not found for section mapping: {md_path}")

        strategy = (self.config.get("strategy") or "heading_match").lower()
        if strategy != "heading_match":
            raise ValueError(f"Unsupported section_mapper strategy: {strategy}")

        md_content = md_path.read_text(encoding="utf-8")
        mapping_doc = build_section_mapping(criteria, md_content)
        mapping_path = run_dir / "mapping.json"
        mapping_path.write_text(json.dumps(mapping_doc, indent=2), encoding="utf-8")

        if log_callback:
            log_callback(f"Mapped {len(mapping_doc['mappings'])} criteria to sections", "info")

        mapping_index = {
            item["criterion_id"]: item for item in mapping_doc["mappings"]
        }
        return {
            "status": "completed",
            "mapping_file": str(mapping_path),
            "mapping": mapping_index,
        }
