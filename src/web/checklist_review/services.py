from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Sequence

BASE_ITEMS = [
    ("Data availability", "Is the dataset (or synthetic data recipe) shared?"),
    ("Code completeness", "Does the paper publish enough detail to reimplement?"),
    ("Hyper-parameters", "Are training and evaluation settings enumerated?"),
    ("Compute footprint", "Is the hardware/runtime budget specified?"),
    ("Evaluation rigor", "Are baselines and ablations reproducible?"),
]


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "item"


def parse_paper_list(raw: str) -> List[str]:
    ids = [line.strip() for line in raw.splitlines() if line.strip()]
    return sorted(set(ids))


def generate_checklist(
    collection_name: str,
    paper_ids: Sequence[str],
    prompt: str,
    collection_payload: Dict[str, Any] | None,
) -> List[Dict[str, Any]]:
    records = collection_payload.get("papers", []) if collection_payload else []
    by_id = {paper["arxiv_id"]: paper for paper in records}

    target_ids = list(paper_ids) or list(by_id.keys())
    entries: List[Dict[str, Any]] = []
    issued_at = datetime.utcnow().isoformat()

    for paper_id in target_ids:
        paper = by_id.get(paper_id)
        if not paper:
            paper = {
                "arxiv_id": paper_id,
                "title": paper_id,
                "summary": "Metadata unavailable in local cache.",
                "url": f"https://arxiv.org/abs/{paper_id}",
            }
        items = []
        for label, question in BASE_ITEMS:
            slug = slugify(f"{paper_id}-{label}")
            items.append(
                {
                    "id": slug,
                    "label": label,
                    "question": question,
                    "status": "pending",
                    "notes": "",
                }
            )
        references = [
            {
                "section": "Abstract",
                "snippet": paper.get("summary", "")[:320],
            },
            {
                "section": "Methods",
                "snippet": "Placeholder for model-assisted extraction.",
            },
            {
                "section": "Results",
                "snippet": "Placeholder for key metrics.",
            },
        ]
        entries.append(
            {
                "paper_id": paper_id,
                "title": paper.get("title", paper_id),
                "prompt": prompt,
                "issued_at": issued_at,
                "collection": collection_name,
                "items": items,
                "references": references,
                "markdown": _render_markdown_summary(paper, items, prompt),
            }
        )
    return entries


def _render_markdown_summary(paper: Dict[str, Any], items: List[Dict[str, str]], prompt: str) -> str:
    lines = [
        f"## {paper.get('title', paper.get('arxiv_id'))}",
        f"Link: {paper.get('url', '')}",
        "",
        f"Prompt summary: {prompt or 'default reproducibility prompt'}",
        "",
        "### Checklist",
    ]
    for item in items:
        lines.append(f"- [ ] {item['label']}: {item['question']}")
    return "\n".join(lines)
