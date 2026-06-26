"""Collection and artifact management for the REST API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from werkzeug.datastructures import FileStorage

from src.core import storage
from src.core.criteria import (
    criteria_set_stem,
    load_criteria_set,
    load_criteria_set_file,
    normalize_criterion,
    save_criteria_set_file,
)
from src.core.criteria_resolver import collection_criteria_path
from src.core.pdf_processing import (
    PDFProcessingError,
    get_default_llm_provider,
    is_rule_based_pdf_metadata_extraction,
    process_pdf_to_markdown_and_metadata,
)
from src.core.workspace import get_collections_dir

_ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".txt", ".md"}


class CollectionServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


REFERENCES_FILE = "references.json"


def _collections_root() -> Path:
    return Path(get_collections_dir())


def _references_path(collection_name: str) -> Path:
    collection_dir = storage._collection_dir(
        _collections_root(), collection_name, create=False
    )
    return collection_dir / REFERENCES_FILE


def list_collections() -> List[Dict[str, Any]]:
    return storage.list_collections(_collections_root())


def create_collection(name: Optional[str] = None) -> Dict[str, Any]:
    collections_root = _collections_root()
    if name:
        from src.core.storage import _slug

        for coll in storage.list_collections(collections_root):
            coll_slug = coll.get("slug") or _slug(coll.get("name", ""))
            if coll_slug == _slug(name):
                raise CollectionServiceError(f"Collection '{name}' already exists", 409)
    created_name = storage.create_new_collection(collections_root, name)
    return {"name": created_name}


def list_artifacts(collection_name: str) -> List[Dict[str, Any]]:
    collections_root = _collections_root()
    if not storage.load_collection(collections_root, collection_name):
        raise CollectionServiceError("Collection not found", 404)
    return storage.list_selected_files(collections_root, collection_name)


def list_source_documents(collection_name: str) -> List[Dict[str, Any]]:
    collections_root = _collections_root()
    collection_dir = storage._collection_dir(
        collections_root, collection_name, create=False
    )
    if not collection_dir.exists():
        raise CollectionServiceError("Collection not found", 404)

    source_dir = storage._source_pdf_dir(collection_dir, create=False)
    if not source_dir.exists():
        return []

    selected = {
        entry.get("filename")
        for entry in storage.load_selected_list(collections_root, collection_name)
    }
    documents: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for pattern in ("*.pdf", "*.md", "*.txt"):
        for doc_path in sorted(source_dir.glob(pattern)):
            if doc_path.name in seen:
                continue
            seen.add(doc_path.name)
            documents.append(
                {
                    "filename": doc_path.name,
                    "artifact_id": doc_path.stem,
                    "role": "artifact" if doc_path.name in selected else "reference",
                    "selected_for_review": doc_path.name in selected,
                }
            )
    return documents


def _ingest_pdf(collection_name: str, pdf_path: Path) -> Dict[str, Any]:
    collections_root = _collections_root()
    collection_dir = storage._collection_dir(
        collections_root, collection_name, create=False
    )
    if not collection_dir.exists():
        raise CollectionServiceError("Collection not found", 404)

    provider_config = get_default_llm_provider()
    if provider_config is None and not is_rule_based_pdf_metadata_extraction():
        raise CollectionServiceError(
            "No LLM provider configured. Set OPENAI_API_KEY (or configure config/providers.yaml) "
            "or use pdf_metadata.method: rule_based in config/providers.yaml.",
            503,
        )

    try:
        metadata = process_pdf_to_markdown_and_metadata(
            pdf_path, collection_dir, provider_config
        )
    except PDFProcessingError as exc:
        raise CollectionServiceError(str(exc), 422) from exc

    return {
        "filename": pdf_path.name,
        "artifact_id": pdf_path.stem,
        "title": metadata.get("title", pdf_path.stem),
    }


def _add_to_selected_list(collection_name: str, filename: str, title: str) -> None:
    collections_root = _collections_root()
    current = storage.load_selected_list(collections_root, collection_name)
    artifact_id = Path(filename).stem
    if any(
        entry.get("filename") == filename or entry.get("artifact_id") == artifact_id
        for entry in current
    ):
        return
    current.append({"filename": filename, "artifact_id": artifact_id, "title": title})
    storage.save_selected_list(collections_root, collection_name, current)


def _ingest_text_document(collection_dir: Path, path: Path) -> Dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise CollectionServiceError("Text uploads must be UTF-8 encoded") from exc

    md_dir = storage._source_md_dir(collection_dir)
    meta_dir = storage._source_metadata_dir(collection_dir)
    stem = path.stem
    md_path = md_dir / f"{stem}.md"
    md_path.write_text(content, encoding="utf-8")

    title = stem.replace("_", " ").replace("-", " ").strip() or stem
    metadata = {"title": title, "source_file": path.name}
    (meta_dir / f"{stem}.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return {"filename": path.name, "artifact_id": stem, "title": title}


def upload_document(
    collection_name: str,
    file: FileStorage,
    *,
    role: str = "artifact",
) -> Dict[str, Any]:
    if not file or not file.filename:
        raise CollectionServiceError("No file uploaded")

    filename = Path(file.filename).name
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise CollectionServiceError("Supported uploads: PDF, TXT, and MD")

    role = (role or "artifact").lower()
    if role not in {"artifact", "rfp", "reference"}:
        raise CollectionServiceError("role must be one of: artifact, rfp, reference")

    collections_root = _collections_root()
    collection_dir = storage._collection_dir(
        collections_root, collection_name, create=True
    )
    source_dir = storage._source_pdf_dir(collection_dir)
    save_path = source_dir / filename
    file.save(save_path)

    if suffix == ".pdf":
        ingested = _ingest_pdf(collection_name, save_path)
    else:
        ingested = _ingest_text_document(collection_dir, save_path)

    select_for_review = role == "artifact"
    if select_for_review:
        _add_to_selected_list(collection_name, ingested["filename"], ingested["title"])

    return {
        **ingested,
        "role": role,
        "selected_for_review": select_for_review,
        "message": (
            "Draft added for review"
            if select_for_review
            else "Reference document stored (not selected for review)"
        ),
    }


def _normalize_criteria_input(raw_items: List[Any]) -> List[Dict[str, Any]]:
    criteria: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_items):
        if isinstance(item, str):
            criteria.append(normalize_criterion(item, index))
        elif isinstance(item, dict):
            criteria.append(normalize_criterion(item, index))
    return [criterion for criterion in criteria if criterion.get("description")]


def parse_custom_criteria_text(text: str) -> List[Dict[str, Any]]:
    stripped = (text or "").strip()
    if not stripped:
        raise CollectionServiceError("Enter at least one criterion")

    if "criteria:" in stripped or stripped.startswith("-"):
        try:
            payload = yaml.safe_load(stripped)
        except yaml.YAMLError as exc:
            raise CollectionServiceError(f"Invalid YAML: {exc}") from exc
        if isinstance(payload, dict) and isinstance(payload.get("criteria"), list):
            return _normalize_criteria_input(payload["criteria"])
        if isinstance(payload, list):
            return _normalize_criteria_input(payload)
        raise CollectionServiceError("YAML must contain a criteria list")

    lines = [
        line.strip()
        for line in stripped.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not lines:
        raise CollectionServiceError("Enter at least one criterion")
    return _normalize_criteria_input(lines)


def save_collection_criteria(
    collection_name: str,
    criteria_set_name: str,
    *,
    criteria: Optional[List[Any]] = None,
    text: Optional[str] = None,
) -> Dict[str, Any]:
    if not criteria_set_name:
        raise CollectionServiceError("criteria_set_name is required")

    if criteria is not None:
        normalized = _normalize_criteria_input(criteria)
    elif text is not None:
        normalized = parse_custom_criteria_text(text)
    else:
        raise CollectionServiceError("Provide criteria or text")

    if not normalized:
        raise CollectionServiceError("At least one criterion is required")

    collections_root = _collections_root()
    collection_dir = storage._collection_dir(
        collections_root, collection_name, create=True
    )
    criteria_dir = collection_dir / "criteria"
    criteria_dir.mkdir(parents=True, exist_ok=True)
    criteria_path = criteria_dir / f"{criteria_set_stem(criteria_set_name)}.yaml"

    criteria_set = load_criteria_set(
        {
            "name": criteria_set_stem(criteria_set_name),
            "criteria": normalized,
            "source": "ui",
        },
        name=criteria_set_stem(criteria_set_name),
    )
    save_criteria_set_file(criteria_path, criteria_set, source="ui")
    return {
        "collection_name": collection_name,
        "criteria_set_name": criteria_set_stem(criteria_set_name),
        "criteria_count": len(normalized),
        "path": str(criteria_path),
    }


def get_collection_criteria(
    collection_name: str, criteria_set_name: str
) -> Dict[str, Any]:
    collections_root = _collections_root()
    criteria_path = collection_criteria_path(
        collections_root, collection_name, criteria_set_name
    )
    if not criteria_path.exists():
        raise CollectionServiceError("Collection criteria not found", 404)
    criteria_set = load_criteria_set_file(criteria_path)
    return {
        "collection_name": collection_name,
        "criteria_set_name": criteria_set_stem(criteria_set_name),
        "criteria": criteria_set.get("criteria", []),
    }


def get_document_content(collection_name: str, filename: str) -> Dict[str, Any]:
    safe_name = Path(filename).name
    if safe_name != filename:
        raise CollectionServiceError("Invalid filename", 400)

    collections_root = _collections_root()
    collection_dir = storage._collection_dir(
        collections_root, collection_name, create=False
    )
    if not collection_dir.exists():
        raise CollectionServiceError("Collection not found", 404)

    source_dir = storage._source_pdf_dir(collection_dir, create=False)
    source_path = source_dir / safe_name
    if not source_path.exists():
        raise CollectionServiceError("Document not found", 404)

    suffix = source_path.suffix.lower()
    md_dir = storage._source_md_dir(collection_dir, create=False)
    extracted_md = md_dir / f"{source_path.stem}.md" if md_dir.exists() else None

    if suffix in {".md", ".txt"}:
        content = source_path.read_text(encoding="utf-8")
        content_type = "text/markdown" if suffix == ".md" else "text/plain"
        source = "uploaded"
    elif extracted_md and extracted_md.exists():
        content = extracted_md.read_text(encoding="utf-8")
        content_type = "text/markdown"
        source = "extracted"
    else:
        raise CollectionServiceError(
            "No readable text content available for this document", 422
        )

    return {
        "collection_name": collection_name,
        "filename": safe_name,
        "content": content,
        "content_type": content_type,
        "source": source,
    }


def set_references(collection_name: str, urls: List[str]) -> Dict[str, Any]:
    collections_root = _collections_root()
    collection_dir = storage._collection_dir(
        collections_root, collection_name, create=False
    )
    if not collection_dir.exists():
        raise CollectionServiceError("Collection not found", 404)

    cleaned = [url.strip() for url in urls if isinstance(url, str) and url.strip()]
    path = _references_path(collection_name)
    path.write_text(json.dumps({"urls": cleaned}, indent=2), encoding="utf-8")
    return {"collection_name": collection_name, "urls": cleaned}


def get_references(collection_name: str) -> List[str]:
    collections_root = _collections_root()
    collection_dir = storage._collection_dir(
        collections_root, collection_name, create=False
    )
    if not collection_dir.exists():
        raise CollectionServiceError("Collection not found", 404)

    path = _references_path(collection_name)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    urls = data.get("urls", [])
    return [url for url in urls if isinstance(url, str)]
