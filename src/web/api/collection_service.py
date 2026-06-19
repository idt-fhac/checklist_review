"""Collection and artifact management for the REST API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from werkzeug.datastructures import FileStorage

from src.core import storage
from src.core.pdf_processing import (
    PDFProcessingError,
    get_default_llm_provider,
    is_rule_based_pdf_metadata_extraction,
    process_pdf_to_markdown_and_metadata,
)
from src.core.workspace import get_collections_dir


class CollectionServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


REFERENCES_FILE = "references.json"


def _collections_root() -> Path:
    return Path(get_collections_dir())


def _references_path(collection_name: str) -> Path:
    collection_dir = storage._collection_dir(_collections_root(), collection_name, create=False)
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
    collection_dir = storage._collection_dir(collections_root, collection_name, create=False)
    if not collection_dir.exists():
        raise CollectionServiceError("Collection not found", 404)

    source_dir = storage._source_pdf_dir(collection_dir, create=False)
    if not source_dir.exists():
        return []

    selected = {entry.get("filename") for entry in storage.load_selected_list(collections_root, collection_name)}
    documents: List[Dict[str, Any]] = []
    for pdf_path in sorted(source_dir.glob("*.pdf")):
        documents.append(
            {
                "filename": pdf_path.name,
                "artifact_id": pdf_path.stem,
                "role": "artifact" if pdf_path.name in selected else "reference",
                "selected_for_review": pdf_path.name in selected,
            }
        )
    return documents


def _ingest_pdf(collection_name: str, pdf_path: Path) -> Dict[str, Any]:
    collections_root = _collections_root()
    collection_dir = storage._collection_dir(collections_root, collection_name, create=False)
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
        metadata = process_pdf_to_markdown_and_metadata(pdf_path, collection_dir, provider_config)
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
    if any(entry.get("filename") == filename or entry.get("artifact_id") == artifact_id for entry in current):
        return
    current.append({"filename": filename, "artifact_id": artifact_id, "title": title})
    storage.save_selected_list(collections_root, collection_name, current)


def upload_document(
    collection_name: str,
    file: FileStorage,
    *,
    role: str = "artifact",
) -> Dict[str, Any]:
    if not file or not file.filename:
        raise CollectionServiceError("No file uploaded")

    filename = Path(file.filename).name
    if not filename.lower().endswith(".pdf"):
        raise CollectionServiceError("Only PDF uploads are supported")

    role = (role or "artifact").lower()
    if role not in {"artifact", "rfp", "reference"}:
        raise CollectionServiceError("role must be one of: artifact, rfp, reference")

    collections_root = _collections_root()
    collection_dir = storage._collection_dir(collections_root, collection_name, create=True)
    source_dir = storage._source_pdf_dir(collection_dir)
    save_path = source_dir / filename
    file.save(save_path)

    ingested = _ingest_pdf(collection_name, save_path)
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


def set_references(collection_name: str, urls: List[str]) -> Dict[str, Any]:
    collections_root = _collections_root()
    collection_dir = storage._collection_dir(collections_root, collection_name, create=False)
    if not collection_dir.exists():
        raise CollectionServiceError("Collection not found", 404)

    cleaned = [url.strip() for url in urls if isinstance(url, str) and url.strip()]
    path = _references_path(collection_name)
    path.write_text(json.dumps({"urls": cleaned}, indent=2), encoding="utf-8")
    return {"collection_name": collection_name, "urls": cleaned}


def get_references(collection_name: str) -> List[str]:
    collections_root = _collections_root()
    collection_dir = storage._collection_dir(collections_root, collection_name, create=False)
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
