from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Generator, Literal, TypedDict

from src.core.pdf_processing import (
    PaperProcessingError,  # Alias for backward compatibility
    PDFProcessingError,
    derive_collection_name,
    get_default_llm_provider,
    is_rule_based_pdf_metadata_extraction,
    process_pdf_to_markdown_and_metadata,
)


class ProgressEvent(TypedDict):
    type: Literal["progress"]
    current: int
    total: int
    filename: str


class ResultEvent(TypedDict):
    type: Literal["result"]
    payload: Dict[str, Any]


def iterate_collection(
    folder_path: str, collection_name_override: str | None = None
) -> Generator[ProgressEvent | ResultEvent, None, None]:
    folder_path = folder_path.strip()
    if not folder_path:
        raise PaperProcessingError("Please provide a folder path containing PDFs.")

    folder = Path(folder_path).expanduser()

    from src.core import storage

    if folder.name == "source":
        collection_dir = folder.parent
        source_dir = folder / "pdf"
        if not source_dir.exists():
            source_dir = folder  # legacy: PDFs directly in source/
    else:
        collection_dir = folder
        source_dir = folder / "source" / "pdf"
        if not source_dir.exists():
            source_dir = folder / "source"  # legacy

    if not source_dir.exists() or not source_dir.is_dir():
        if any(folder.glob("*.pdf")):
            source_dir = folder
            collection_dir = folder

    pdf_files = sorted(p for p in source_dir.glob("*.pdf") if p.is_file())
    if not pdf_files and source_dir != collection_dir:
        root_files = sorted(p for p in collection_dir.glob("*.pdf") if p.is_file())
        if root_files:
            source_dir = collection_dir
            pdf_files = root_files

    total = len(pdf_files)

    # Get LLM provider only when the selected extraction method needs one.
    provider_config = get_default_llm_provider()
    if not provider_config and not is_rule_based_pdf_metadata_extraction():
        raise PaperProcessingError(
            "No LLM provider configured. Please add an LLM provider in settings or use rule-based PDF metadata extraction."
        )

    # Process all PDFs using the new method
    for index, pdf in enumerate(pdf_files, start=1):
        yield ProgressEvent(
            type="progress", current=index, total=total, filename=pdf.name
        )

        # Check if already processed (metadata in source/metadata or legacy source_extracted)
        meta_dir = storage._source_metadata_dir(collection_dir, create=False)
        extracted_json_path = (
            meta_dir / f"{pdf.stem}.json"
            if meta_dir.exists()
            else collection_dir / "source_extracted" / f"{pdf.stem}.json"
        )
        if not extracted_json_path.exists():
            try:
                process_pdf_to_markdown_and_metadata(
                    pdf, collection_dir, provider_config
                )
            except (PDFProcessingError, Exception):
                # Skip this PDF if processing fails
                continue

    # Create simplified paper records - only essential info
    # All other metadata (title, abstract, authors) is stored in source/metadata JSON files
    serialized_records = []
    for pdf in pdf_files:
        try:
            rel_path = pdf.relative_to(collection_dir)
        except ValueError:
            rel_path = Path("source/pdf") / pdf.name
        serialized_records.append(
            {
                "paper_id": pdf.stem,
                "filename": pdf.name,
                "file_path": str(rel_path),
            }
        )

    collection_name = collection_name_override or derive_collection_name(
        str(collection_dir)
    )
    try:
        source_folder_rel = source_dir.relative_to(collection_dir)
    except ValueError:
        source_folder_rel = Path("source/pdf")

    payload = {
        "collection_name": collection_name,
        "source_folder": str(source_folder_rel),
        "papers": serialized_records,
    }
    yield ResultEvent(type="result", payload=payload)


def process_collection(folder_path: str) -> Dict[str, Any]:
    result: Dict[str, Any] | None = None
    for event in iterate_collection(folder_path):
        if event["type"] == "result":
            result = event["payload"]
    if result is None:
        raise PaperProcessingError("Processing did not produce a result.")
    return result
