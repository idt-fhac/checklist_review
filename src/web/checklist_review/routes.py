from __future__ import annotations

import json
import logging
import multiprocessing
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from flask import (
    Blueprint,
    Response,
    flash,
    jsonify,
    render_template,
    request,
    send_file,
    stream_with_context,
)

from src.core import storage, task_persistence
from src.core.task_manager import TaskManager, TaskStatus
from src.core.workspace import get_collections_dir
from src.review_workflow.engine.pipeline_loader import build_review_process_definition
from src.review_workflow.engine.review_process import ReviewProcess
from src.review_workflow.review_runner import run_review_subprocess
from src.web.checklist_review import services

checklist_review_bp = Blueprint(
    "checklist_review",
    __name__,
    url_prefix="/checklist_review",
    template_folder="templates",
)
logger = logging.getLogger(__name__)


def _normalize_criteria_input(raw_items: List[Any]) -> List[Dict[str, Any]]:
    from src.core.criteria import normalize_criterion

    criteria: List[Dict[str, Any]] = []
    for i, item in enumerate(raw_items):
        if isinstance(item, str):
            criteria.append(normalize_criterion(item, i))
            continue
        if isinstance(item, dict):
            description = (
                item.get("description")
                or item.get("text")
                or item.get("question")
                or ""
            )
            criteria.append(
                normalize_criterion(
                    {
                        "id": item.get("id"),
                        "description": description,
                        **{
                            k: v
                            for k, v in item.items()
                            if k not in ("text", "question")
                        },
                    },
                    i,
                )
            )
    return [c for c in criteria if c.get("description")]


def _write_criteria_set_file(
    path: Path, name: str, criteria: List[Dict[str, Any]], **extra: Any
) -> Dict[str, Any]:
    from src.core.criteria import load_criteria_set, save_criteria_set_file

    payload = {"name": name, "criteria": criteria, **extra}
    criteria_set = load_criteria_set(payload, name=name)
    save_criteria_set_file(path, criteria_set, **extra)
    return criteria_set


@checklist_review_bp.route("/static/<path:filename>")
def checklist_review_static(filename):
    from flask import send_from_directory

    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    static_dir = base_dir / "src" / "web" / "checklist_review" / "static"
    return send_from_directory(str(static_dir), filename)


@checklist_review_bp.route("/", methods=["GET", "POST"])
def index():
    collections_root = get_collections_dir()
    context: Dict[str, Any] = {
        "active_tab": "checklist_review",
        "checklist_result": None,
    }

    if request.method == "GET":
        try:
            storage.delete_collection(collections_root, "Temporary")
            storage.create_new_collection(collections_root, "Temporary")
        except Exception as e:
            logger.error(f"Failed to reset Temporary collection: {e}")

    collections_list = storage.list_collections(collections_root)
    collection_options = []
    for item in collections_list:
        collection_slug = item.get("slug") or item["name"]
        collection_options.append(
            {
                "name": item["name"],
                "slug": collection_slug,
                "selected_files": storage.list_selected_files(
                    collections_root, collection_slug
                ),
            }
        )
    context["collections"] = collection_options

    if request.method == "POST":
        form_id = request.form.get("form_id")
        try:
            if form_id == "checklist_form":
                collection_choice = request.form.get("collection_choice", "")
                raw_artifact_ids = request.form.get("artifact_ids", "")
                prompt = request.form.get("prompt", "")
                artifact_ids = services.parse_paper_list(raw_artifact_ids)

                collection_payload = (
                    storage.load_collection(collections_root, collection_choice)
                    if collection_choice
                    else None
                )
                entries = services.generate_checklist(
                    collection_choice, artifact_ids, prompt, collection_payload
                )
                saved_path = storage.save_checklist(
                    collections_root, collection_choice or "adhoc", entries
                )

                context["checklist_result"] = {
                    "entries": entries,
                    "path": saved_path,
                }
                flash(
                    f"Checklist prototype created for {len(entries)} papers.", "success"
                )
        except ValueError as err:
            flash(str(err), "danger")

    return render_template("checklist_review/index.html", **context)


@checklist_review_bp.get("/api/artifacts")
def api_list_artifacts():
    collection_name = request.args.get("collection_name")
    if not collection_name:
        return jsonify([])

    collections_root = get_collections_dir()
    papers = storage.list_selected_files(collections_root, collection_name)
    return jsonify(papers)


@checklist_review_bp.get("/api/artifact-details")
def api_get_artifact_details():
    collection_name = request.args.get("collection_name")
    artifact_id = request.args.get("artifact_id")

    if not collection_name or not artifact_id:
        return jsonify({"error": "Missing collection_name or artifact_id"}), 400

    collections_root = get_collections_dir()
    collection_dir = storage._collection_dir(
        collections_root, collection_name, create=False
    )
    paper_stem = Path(artifact_id).stem
    meta_dir = storage._source_metadata_dir(collection_dir, create=False)
    json_path = meta_dir / f"{paper_stem}.json" if meta_dir.exists() else None
    if not json_path or not json_path.exists():
        json_path = collection_dir / "source_extracted" / f"{paper_stem}.json"  # legacy
    if json_path.exists():
        try:
            with json_path.open("r", encoding="utf-8") as f:
                metadata = json.load(f)
                return jsonify(
                    {
                        "title": metadata.get("title", artifact_id),
                        "abstract": metadata.get("abstract", ""),
                        "summary": metadata.get(
                            "abstract", ""
                        ),  # Alias for compatibility
                        "authors": metadata.get("authors", []),
                        "artifact_id": artifact_id,
                        "filename": artifact_id + ".pdf",  # Best guess
                    }
                )
        except Exception as e:
            logger.error(f"Error reading paper metadata: {e}")
            return jsonify({"error": f"Failed to read metadata: {str(e)}"}), 500

    # If metadata not found, return basic info
    return jsonify(
        {
            "title": artifact_id,
            "abstract": "",
            "summary": "",
            "authors": [],
            "artifact_id": artifact_id,
            "filename": artifact_id + ".pdf",
        }
    )


@checklist_review_bp.delete("/api/artifacts/<artifact_id>")
def api_delete_artifact(artifact_id: str):
    collection_name = request.args.get("collection_name")
    if not collection_name:
        return jsonify({"error": "Missing collection_name"}), 400

    collections_root = get_collections_dir()
    collection_dir = storage._collection_dir(
        collections_root, collection_name, create=False
    )

    # Normalize artifact_id (remove .pdf extension if present for matching)
    artifact_id_stem = Path(artifact_id).stem

    # Load selected list to find the paper
    selected_files = storage.load_selected_list(collections_root, collection_name)
    paper_entry = None

    # Try to find paper by artifact_id, filename (with or without .pdf), or title
    for entry in selected_files:
        entry_artifact_id = entry.get("artifact_id", "")
        entry_filename = entry.get("filename", "")
        entry_title = entry.get("title", "")

        # Normalize entry filename stem for comparison
        entry_filename_stem = Path(entry_filename).stem if entry_filename else ""

        if (
            entry_artifact_id == artifact_id
            or entry_artifact_id == artifact_id_stem
            or entry_filename == artifact_id
            or entry_filename_stem == artifact_id_stem
            or entry_title == artifact_id
        ):
            paper_entry = entry
            break

    if not paper_entry:
        # Also try remove_paper in case it's in the collection.json
        # Try both with and without .pdf extension
        success = storage.remove_paper(collections_root, collection_name, artifact_id)
        if not success and artifact_id_stem != artifact_id:
            success = storage.remove_paper(
                collections_root, collection_name, artifact_id_stem
            )
        if not success:
            return jsonify({"error": "Paper not found or unable to delete."}), 404
        return jsonify({"message": f"Paper '{artifact_id}' removed from collection."})

    # Get filename for deletion
    filename = paper_entry.get("filename")
    if not filename:
        # Try to construct from artifact_id
        filename = paper_entry.get("artifact_id", artifact_id)
        if not filename.endswith(".pdf"):
            filename = f"{filename}.pdf"

    # Delete PDF and extracted files (new layout: source/pdf, source/md, source/metadata)
    pdf_stem = Path(filename).stem
    source_file = storage._source_pdf_dir(collection_dir, create=False) / filename
    if not source_file.exists():
        source_file = collection_dir / "source" / filename  # legacy
    if source_file.exists():
        try:
            source_file.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete source file {source_file}: {e}")
    md_dir = storage._source_md_dir(collection_dir, create=False)
    meta_dir = storage._source_metadata_dir(collection_dir, create=False)
    for d, ext in [(md_dir, ".md"), (meta_dir, ".json")]:
        if d.exists():
            f = d / f"{pdf_stem}{ext}"
            if f.exists():
                try:
                    f.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete {f}: {e}")
    legacy_extracted = collection_dir / "source_extracted"
    if legacy_extracted.exists():
        for ext in (".md", ".json"):
            f = legacy_extracted / f"{pdf_stem}{ext}"
            if f.exists():
                try:
                    f.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete {f}: {e}")

    # Remove from selected list - match by all possible identifiers
    entry_artifact_id = paper_entry.get("artifact_id", "")
    entry_filename = paper_entry.get("filename", "")
    entry_title = paper_entry.get("title", "")

    updated_selected = [
        entry
        for entry in selected_files
        if not (
            (entry.get("artifact_id") == entry_artifact_id and entry_artifact_id)
            or (entry.get("filename") == entry_filename and entry_filename)
            or (entry.get("title") == entry_title and entry_title)
        )
    ]
    storage.save_selected_list(collections_root, collection_name, updated_selected)

    # Remove review data (LLM answers, human_verification.json, etc.) from all review processes
    storage.remove_paper_from_review_processes(
        collections_root, collection_name, filename
    )

    # Also try to remove from collection.json if it exists there
    try:
        storage.remove_paper(collections_root, collection_name, artifact_id)
        if artifact_id_stem != artifact_id:
            storage.remove_paper(collections_root, collection_name, artifact_id_stem)
    except Exception:
        pass  # Ignore if not in collection.json

    return jsonify({"message": f"Paper '{artifact_id}' removed from collection."})


@checklist_review_bp.post("/api/artifacts/upload")
def api_upload_artifact():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files uploaded."}), 400

    collection_name = request.form.get("collection_name")
    if not collection_name:
        return jsonify({"error": "Missing collection_name"}), 400

    # Check for LLM provider only when the selected extraction method needs one.
    from src.core.pdf_processing import (
        get_default_llm_provider,
        is_rule_based_pdf_metadata_extraction,
    )

    provider_config = get_default_llm_provider()
    if provider_config is None and not is_rule_based_pdf_metadata_extraction():
        return jsonify(
            {
                "error": "No LLM provider configured. Please add an LLM provider in settings or use rule-based PDF metadata extraction."
            }
        ), 400

    collections_root = get_collections_dir()
    collection_dir = storage._collection_dir(
        collections_root, collection_name, create=False
    )
    source_dir = storage._source_pdf_dir(collection_dir)
    md_dir = storage._source_md_dir(collection_dir)
    meta_dir = storage._source_metadata_dir(collection_dir)

    # Filter and save PDF files
    pdf_files = []
    for file in files:
        if file and file.filename.lower().endswith(".pdf"):
            filename = Path(file.filename).name
            save_path = source_dir / filename
            file.save(save_path)
            pdf_files.append(save_path)

    if not pdf_files:
        return jsonify({"error": "No valid PDF files saved."}), 400

    def generate():
        total = len(pdf_files)
        processed_count = 0

        try:
            from src.core.pdf_processing import (
                PDFProcessingError,
                extract_first_page,
                extract_metadata_from_first_page,
                pdf_to_markdown,
            )

            # Process each paper sequentially: extract MD then metadata; progress bar advances per paper
            for paper_index, pdf_path in enumerate(pdf_files, start=1):
                pdf_stem = pdf_path.stem
                md_path = md_dir / f"{pdf_stem}.md"
                json_path = meta_dir / f"{pdf_stem}.json"

                # --- Step 1: Convert PDF to markdown if needed ---
                if not md_path.exists():
                    yield _sse_message(
                        "progress",
                        {
                            "completed": processed_count,
                            "total": total,
                            "paper_index": paper_index,
                            "message": f"Converting {pdf_path.name} to Markdown...",
                        },
                    )
                    try:
                        pdf_to_markdown(pdf_path, md_path)
                    except PDFProcessingError as e:
                        yield _sse_message(
                            "error",
                            {
                                "filename": pdf_path.name,
                                "message": f"Failed to convert {pdf_path.name} to Markdown: {str(e)}",
                            },
                        )
                        continue
                    except Exception as e:
                        yield _sse_message(
                            "error",
                            {
                                "filename": pdf_path.name,
                                "message": f"Unexpected error converting {pdf_path.name}: {str(e)}",
                            },
                        )
                        continue

                # --- Step 2: Extract metadata if needed ---
                if not json_path.exists():
                    yield _sse_message(
                        "progress",
                        {
                            "completed": processed_count,
                            "total": total,
                            "paper_index": paper_index,
                            "message": f"Extracting metadata from {pdf_path.name}...",
                        },
                    )
                    try:
                        md_content = md_path.read_text(encoding="utf-8")
                        first_page = extract_first_page(md_content)
                        metadata = extract_metadata_from_first_page(
                            first_page, provider_config
                        )
                        json_path.write_text(
                            json.dumps(metadata, indent=2), encoding="utf-8"
                        )
                    except PDFProcessingError as e:
                        yield _sse_message(
                            "error",
                            {
                                "filename": pdf_path.name,
                                "message": f"Failed to extract metadata from {pdf_path.name}: {str(e)}",
                            },
                        )
                        continue
                    except Exception as e:
                        yield _sse_message(
                            "error",
                            {
                                "filename": pdf_path.name,
                                "message": f"Unexpected error extracting metadata from {pdf_path.name}: {str(e)}",
                            },
                        )
                        continue

                # Paper fully processed
                processed_count += 1
                yield _sse_message(
                    "progress",
                    {
                        "completed": processed_count,
                        "total": total,
                        "paper_index": paper_index,
                        "message": f"Done with {pdf_path.name}.",
                    },
                )

            # Update selected list with newly processed papers
            try:
                current_list = storage.load_selected_list(
                    collections_root, collection_name
                )
                for pdf_path in pdf_files:
                    pdf_stem = pdf_path.stem
                    exists = any(
                        p.get("filename") == pdf_path.name
                        or p.get("artifact_id") == pdf_stem
                        for p in current_list
                    )
                    if not exists:
                        # Try to load metadata for title
                        json_path = meta_dir / f"{pdf_stem}.json"
                        title = pdf_path.name
                        if json_path.exists():
                            try:
                                metadata = json.loads(
                                    json_path.read_text(encoding="utf-8")
                                )
                                title = metadata.get("title", pdf_path.name)
                            except Exception:
                                pass

                        current_list.append(
                            {
                                "filename": pdf_path.name,
                                "artifact_id": pdf_stem,
                                "title": title,
                            }
                        )
                storage.save_selected_list(
                    collections_root, collection_name, current_list
                )
            except Exception:
                pass  # Continue even if list update fails

            # Complete
            yield _sse_message(
                "complete",
                {
                    "collection": collection_name,
                    "processed_count": processed_count,
                    "total_count": total,
                },
            )
        except Exception as exc:
            yield _sse_message("error", {"message": f"Unexpected error: {exc}"})

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@checklist_review_bp.get("/api/components")
def api_list_components():
    grouped = list_components_metadata()
    components = []
    for group in grouped.values():
        components.extend(group)
    return jsonify(components)


@checklist_review_bp.get("/api/providers")
def api_list_providers():
    from src.web.settings.services import SettingsManager

    return jsonify(SettingsManager.list_providers_for_api())


@checklist_review_bp.post("/api/simulate-criteria-set")
def simulate_checklist():
    payload = request.get_json(silent=True) or {}
    items = payload.get("items")
    if not isinstance(items, list):
        return jsonify({"error": "Items are required."}), 400

    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    from src.core.storage import _criteria_sets_dir

    checklist_dir = _criteria_sets_dir(base_dir)
    checklist_dir.mkdir(parents=True, exist_ok=True)

    generated_files: List[str] = []

    def random_criteria(count: int = 3):
        return [
            {"id": f"req-{i + 1}", "description": f"Criterion {i + 1}"}
            for i in range(count)
        ]

    for entry in items:
        filename = (
            entry.get("filename") or entry.get("artifact_id") or entry.get("title")
        )
        if not filename:
            continue
        target = checklist_dir / f"{Path(filename).stem}.yaml"
        _write_criteria_set_file(
            target,
            Path(filename).stem,
            random_criteria(),
            generated_at=datetime.utcnow().isoformat(),
            artifact_id=entry.get("artifact_id"),
            title=entry.get("title"),
        )
        generated_files.append(str(target))

    return jsonify(
        {"message": f"Simulated criteria set saved ({len(generated_files)} files)."}
    )


@checklist_review_bp.get("/api/criteria-sets")
def api_list_criteria_sets():
    """List all checklists from workspaces/guest/checklists (global, not per collection)"""
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    all_checklists = storage.list_criteria_sets(base_dir)
    # Sort by creation date (newest first)
    all_checklists.sort(
        key=lambda x: (
            x.get("created_at")
            if isinstance(x.get("created_at"), datetime)
            else datetime(1970, 1, 1)
        ),
        reverse=True,
    )
    return jsonify(all_checklists)


def _sse_message(event: str, payload: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@checklist_review_bp.post("/api/criteria-sets/upload")
def api_upload_checklist():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    from src.core.pdf_processing import (
        PDFProcessingError,
        extract_checklist_questions_from_pdf,
        get_checklist_extraction_llm_provider,
    )
    from src.core.storage import _criteria_sets_dir

    checklist_dir = _criteria_sets_dir(base_dir)
    checklist_dir.mkdir(parents=True, exist_ok=True)

    filename = file.filename
    file_stem = Path(filename).stem

    # For PDF files, we'll extract and save as JSON only (no PDF storage)
    # For JSON files, save directly
    if filename.lower().endswith(".pdf"):
        # Save PDF temporarily for extraction, then delete it
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            pdf_path = Path(tmp_file.name)
            file.save(pdf_path)
    else:
        suffix = Path(filename).suffix.lower()
        if suffix not in (".yaml", ".yml", ".json"):
            return jsonify(
                {"error": "Criteria set uploads must be .yaml or .yml files"}
            ), 400
        pdf_path = None
        uploaded_path = checklist_dir / filename
        file.save(uploaded_path)

    def generate():
        try:
            # Stage 1: Upload complete
            yield _sse_message(
                "stage_start",
                {
                    "stage": "upload",
                    "stage_name": "Uploading Criteria Set",
                    "filename": filename,
                },
            )

            if filename.lower().endswith(".pdf"):
                yield _sse_message(
                    "progress",
                    {
                        "stage": "upload",
                        "progress": 50,
                        "message": f"Processing {filename}...",
                        "filename": filename,
                    },
                )

                # Stage 2: Extract questions from PDF
                yield _sse_message(
                    "stage_start",
                    {
                        "stage": "extraction",
                        "stage_name": "Extracting Questions",
                        "filename": filename,
                    },
                )

                provider_config = get_checklist_extraction_llm_provider()
                if provider_config:
                    yield _sse_message(
                        "progress",
                        {
                            "stage": "extraction",
                            "progress": 10,
                            "message": "Extracting text from PDF...",
                            "filename": filename,
                        },
                    )

                    extracted = extract_checklist_questions_from_pdf(
                        pdf_path, provider_config
                    )
                    criteria = _normalize_criteria_input(extracted)

                    yield _sse_message(
                        "progress",
                        {
                            "stage": "extraction",
                            "progress": 80,
                            "message": f"Extracted {len(criteria)} criteria",
                            "filename": filename,
                        },
                    )

                    yaml_path = checklist_dir / f"{file_stem}.yaml"
                    _write_criteria_set_file(
                        yaml_path,
                        file_stem,
                        criteria,
                        source="extracted_from_pdf",
                    )

                    # Delete temporary PDF file
                    try:
                        if pdf_path and pdf_path.exists():
                            pdf_path.unlink()
                    except Exception as e:
                        logger.warning(f"Failed to delete temporary PDF: {e}")

                    yield _sse_message(
                        "progress",
                        {
                            "stage": "extraction",
                            "progress": 100,
                            "message": "Questions saved successfully",
                            "filename": filename,
                        },
                    )

                    yield _sse_message(
                        "complete",
                        {
                            "filename": filename,
                            "criteria_extracted": len(criteria),
                            "message": "Criteria set uploaded and criteria extracted successfully",
                        },
                    )
                else:
                    # Delete temporary PDF and return error
                    try:
                        if pdf_path and pdf_path.exists():
                            pdf_path.unlink()
                    except Exception:
                        pass
                    yield _sse_message(
                        "error",
                        {
                            "filename": filename,
                            "message": "No LLM provider configured for extraction. Please configure one in settings.",
                        },
                    )
            else:
                import yaml as yaml_lib

                from src.core.criteria import (
                    criteria_set_path,
                    load_criteria_set,
                    save_criteria_set_file,
                )

                yield _sse_message(
                    "progress",
                    {
                        "stage": "upload",
                        "progress": 50,
                        "message": f"Validating {filename}...",
                        "filename": filename,
                    },
                )
                raw = uploaded_path.read_text(encoding="utf-8")
                if uploaded_path.suffix.lower() == ".json":
                    payload = json.loads(raw)
                else:
                    payload = yaml_lib.safe_load(raw)
                criteria_set = load_criteria_set(payload, name=file_stem)
                dest = criteria_set_path(checklist_dir, file_stem)
                save_criteria_set_file(dest, criteria_set)
                if uploaded_path != dest and uploaded_path.exists():
                    uploaded_path.unlink()

                yield _sse_message(
                    "progress",
                    {
                        "stage": "upload",
                        "progress": 100,
                        "message": f"Saved {dest.name}",
                        "filename": filename,
                    },
                )

                yield _sse_message(
                    "complete",
                    {
                        "filename": dest.name,
                        "message": "Criteria set uploaded successfully",
                    },
                )
        except PDFProcessingError as e:
            logger.error(f"Error extracting checklist questions: {e}")
            # Clean up temporary PDF if it exists
            try:
                if pdf_path and pdf_path.exists():
                    pdf_path.unlink()
            except Exception:
                pass
            yield _sse_message(
                "error",
                {
                    "filename": filename,
                    "message": f"Question extraction failed: {str(e)}",
                },
            )
        except Exception as e:
            logger.error(
                f"Unexpected error during checklist upload: {e}", exc_info=True
            )
            # Clean up temporary PDF if it exists
            try:
                if pdf_path and pdf_path.exists():
                    pdf_path.unlink()
            except Exception:
                pass
            yield _sse_message(
                "error",
                {"filename": filename, "message": f"Unexpected error: {str(e)}"},
            )

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@checklist_review_bp.get("/api/criteria-sets/<criteria_set_name>/view")
def api_view_criteria_set(criteria_set_name):
    """View a criteria set from the active workspace."""
    from src.core.criteria import (
        find_criteria_set_path,
        load_criteria_set_file,
    )

    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    from src.core.storage import _criteria_sets_dir

    criteria_dir = _criteria_sets_dir(base_dir)
    criteria_file = find_criteria_set_path(criteria_dir, criteria_set_name)

    if criteria_file is None:
        return jsonify({"error": "Criteria set not found"}), 404

    try:
        criteria_set = load_criteria_set_file(criteria_file)
        return jsonify(
            {
                "type": "yaml",
                "name": criteria_set_name,
                "criteria": criteria_set.get("criteria", []),
                "source": criteria_set.get("source"),
            }
        )
    except Exception as e:
        logger.error(f"Error reading criteria set YAML: {e}")
        return jsonify({"error": f"Failed to read criteria set: {str(e)}"}), 500


@checklist_review_bp.post("/api/criteria-sets/<criteria_set_name>/rename")
def api_rename_checklist(criteria_set_name):
    """Rename a checklist in workspaces/guest/checklists (global, not per collection)"""
    data = request.get_json()
    new_name = data.get("new_name")

    if not new_name:
        return jsonify({"error": "Missing new_name"}), 400

    from src.core.criteria import criteria_set_path, find_criteria_set_path

    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    from src.core.storage import _criteria_sets_dir

    checklist_dir = _criteria_sets_dir(base_dir)

    criteria_file = find_criteria_set_path(checklist_dir, criteria_set_name)
    new_file = criteria_set_path(checklist_dir, new_name)

    if criteria_file is None:
        return jsonify({"error": "Checklist not found"}), 404

    if new_file.exists():
        return jsonify({"error": "A checklist with this name already exists"}), 400

    try:
        criteria_file.rename(new_file)

        # Rename checklist folders in all collections
        collections_root = get_collections_dir()
        folder_result = storage.rename_checklist_folders(
            collections_root, criteria_set_name, new_name
        )

        if folder_result["errors"]:
            logger.warning(
                f"Some checklist folders could not be renamed: {folder_result['errors']}"
            )

        message = "Checklist renamed successfully"
        if folder_result["renamed"]:
            message += f" ({len(folder_result['renamed'])} folder(s) renamed)"
        if folder_result["errors"]:
            message += f" ({len(folder_result['errors'])} error(s))"

        return jsonify(
            {"message": message, "new_name": new_name, "folder_result": folder_result}
        )
    except Exception as e:
        logger.error(f"Error renaming checklist: {e}")
        return jsonify({"error": f"Failed to rename checklist: {str(e)}"}), 500


@checklist_review_bp.delete("/api/criteria-sets/<criteria_set_name>")
def api_delete_checklist(criteria_set_name):
    """Delete a checklist from workspaces/guest/checklists (global, not per collection)"""
    from src.core.criteria import find_criteria_set_path

    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    from src.core.storage import _criteria_sets_dir

    checklist_dir = _criteria_sets_dir(base_dir)

    criteria_file = find_criteria_set_path(checklist_dir, criteria_set_name)

    if criteria_file is None:
        return jsonify({"error": "Checklist not found"}), 404

    try:
        criteria_file.unlink()

        # Delete checklist folders in all collections
        collections_root = get_collections_dir()
        folder_result = storage.delete_checklist_folders(
            collections_root, criteria_set_name
        )

        if folder_result["errors"]:
            logger.warning(
                f"Some checklist folders could not be deleted: {folder_result['errors']}"
            )

        message = "Checklist deleted successfully"
        if folder_result["deleted"]:
            message += f" ({len(folder_result['deleted'])} folder(s) deleted)"
        if folder_result["errors"]:
            message += f" ({len(folder_result['errors'])} error(s))"

        return jsonify({"message": message, "folder_result": folder_result})
    except Exception as e:
        logger.error(f"Error deleting checklist: {e}")
        return jsonify({"error": f"Failed to delete checklist: {str(e)}"}), 500


@checklist_review_bp.post("/api/criteria-sets/create")
def api_create_criteria_set():
    """Create a criteria set in the active workspace."""
    data = request.get_json()
    criteria_set_name = data.get("name")
    raw_criteria = data.get("criteria", [])

    if not criteria_set_name:
        return jsonify({"error": "Missing name"}), 400

    criteria = _normalize_criteria_input(raw_criteria)
    if not criteria:
        return jsonify({"error": "At least one criterion is required"}), 400

    from src.core.criteria import criteria_set_path

    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    from src.core.storage import _criteria_sets_dir

    criteria_dir = _criteria_sets_dir(base_dir)
    criteria_dir.mkdir(parents=True, exist_ok=True)

    criteria_file = criteria_set_path(criteria_dir, criteria_set_name)
    if criteria_file.exists():
        return jsonify({"error": "A criteria set with this name already exists"}), 400

    try:
        _write_criteria_set_file(criteria_file, criteria_set_name, criteria)
        return jsonify(
            {"message": "Criteria set created successfully", "name": criteria_set_name}
        )
    except Exception as e:
        logger.error(f"Error creating criteria set: {e}")
        return jsonify({"error": f"Failed to create criteria set: {str(e)}"}), 500


@checklist_review_bp.put("/api/criteria-sets/<criteria_set_name>")
def api_update_criteria_set(criteria_set_name):
    """Update a criteria set in the active workspace."""
    data = request.get_json()
    raw_criteria = data.get("criteria", [])

    criteria = _normalize_criteria_input(raw_criteria)
    if not criteria:
        return jsonify({"error": "At least one criterion is required"}), 400

    from src.core.criteria import (
        find_criteria_set_path,
        load_criteria_set_file,
    )

    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    from src.core.storage import _criteria_sets_dir

    criteria_dir = _criteria_sets_dir(base_dir)
    criteria_file = find_criteria_set_path(criteria_dir, criteria_set_name)

    if criteria_file is None:
        return jsonify({"error": "Criteria set not found"}), 404

    try:
        existing = load_criteria_set_file(criteria_file)
        extra = {}
        for key in ("source", "generated_at"):
            if existing.get(key) is not None:
                extra[key] = existing[key]
        _write_criteria_set_file(criteria_file, criteria_set_name, criteria, **extra)
        return jsonify(
            {"message": "Criteria set updated successfully", "name": criteria_set_name}
        )
    except Exception as e:
        logger.error(f"Error updating criteria set: {e}")
        return jsonify({"error": f"Failed to update criteria set: {str(e)}"}), 500


@checklist_review_bp.post("/api/criteria-sets/<criteria_set_name>/criteria")
def api_get_criteria_set_criteria(criteria_set_name):
    """Return criteria from a criteria set JSON file."""
    from src.core.criteria import (
        criteria_for_evaluator,
        find_criteria_set_path,
        load_criteria_set_file,
    )
    from src.core.storage import _criteria_sets_dir

    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    criteria_path = find_criteria_set_path(
        _criteria_sets_dir(base_dir), criteria_set_name
    )
    if criteria_path is None:
        return jsonify({"error": f"Criteria set '{criteria_set_name}' not found"}), 404
    criteria_set = load_criteria_set_file(criteria_path)
    criteria = criteria_for_evaluator(criteria_set)
    return jsonify({"criteria": criteria, "count": len(criteria)})


@checklist_review_bp.get("/api/pipelines")
def api_list_pipelines():
    """List pipelines from config/pipelines/."""
    from src.core.config_loader import list_pipelines

    return jsonify(list_pipelines())


@checklist_review_bp.post("/api/run-process")
def api_run_process():
    data = request.get_json()
    collection_name = data.get("collection_name")
    pipeline_id = data.get("pipeline_id")
    criteria_set_name = data.get("criteria_set_name")
    target_artifact = data.get("target_artifact")

    if not collection_name:
        return jsonify({"error": "Missing collection_name"}), 400
    if not pipeline_id:
        return jsonify({"error": "Missing pipeline id (pipeline_id)"}), 400
    if not criteria_set_name:
        return jsonify({"error": "Missing criteria_set_name"}), 400

    collections_root = get_collections_dir()
    selected_artifacts = storage.list_selected_files(collections_root, collection_name)

    if target_artifact:
        selected_artifacts = [
            p for p in selected_artifacts if p.get("filename") == target_artifact
        ]

    try:
        review_process_def = build_review_process_definition(pipeline_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    execution_name = review_process_def.get("name") or pipeline_id

    results = []

    for artifact in selected_artifacts:
        artifact_name = artifact.get("filename")
        if not artifact_name:
            continue

        if pipeline_id and storage.process_result_exists(
            collections_root,
            collection_name,
            pipeline_id,
            artifact_name,
            criteria_set_name,
        ):
            logger.info(
                f"Skipping {artifact_name}, answer already exists for {pipeline_id} with checklist {criteria_set_name}"
            )
            continue

        try:
            process_instance = ReviewProcess(
                review_process_def, collections_root=collections_root
            )

            run_result = process_instance.execute(
                collection_name=collection_name,
                artifact_name=artifact_name,
                criteria_set_name=criteria_set_name,
            )
            result_summary = {
                "artifact_id": artifact.get("artifact_id", artifact_name),
                "filename": artifact_name,
                "status": "completed",
            }
            if run_result and run_result.get("token_usage"):
                result_summary["token_usage"] = run_result["token_usage"]
            results.append(result_summary)

        except Exception as e:
            logger.error(f"Failed to process {artifact_name}: {e}")
            results.append(
                {
                    "artifact_id": artifact.get("artifact_id", artifact_name),
                    "status": "failed",
                    "error": str(e),
                }
            )

    return jsonify(
        {
            "message": f"Processed {len(results)} papers (skipped others)",
            "results": results,
        }
    )


@checklist_review_bp.get("/api/results")
def api_list_results():
    collection_name = request.args.get("collection_name")
    artifact_id = request.args.get("artifact_id")
    pipeline_id = request.args.get("pipeline_id")
    criteria_set_name = request.args.get("criteria_set_name")

    if not collection_name:
        return jsonify([])

    collections_root = get_collections_dir()

    if artifact_id:
        res = storage.load_evaluation(
            collections_root,
            collection_name,
            artifact_id,
            pipeline_id,
            criteria_set_name,
        )
        if res:
            return jsonify(res)
        return jsonify({"status": "not_found", "message": "No result found"}), 200
    else:
        results = storage.list_evaluations(
            collections_root, collection_name, pipeline_id, criteria_set_name
        )
        return jsonify(results)


@checklist_review_bp.delete("/api/results/<artifact_id>")
def api_delete_result(artifact_id):
    collection_name = request.args.get("collection_name")
    pipeline_id = request.args.get("pipeline_id")
    criteria_set_name = request.args.get("criteria_set_name")

    if not collection_name:
        return jsonify({"error": "Missing collection_name"}), 400

    collections_root = get_collections_dir()
    success = storage.delete_evaluation(
        collections_root, collection_name, artifact_id, pipeline_id, criteria_set_name
    )
    return jsonify({"success": success})


@checklist_review_bp.delete("/api/results")
def api_delete_all_results():
    collection_name = request.args.get("collection_name")
    pipeline_id = request.args.get("pipeline_id")
    criteria_set_name = request.args.get("criteria_set_name")

    if not all([collection_name, pipeline_id, criteria_set_name]):
        return jsonify(
            {"error": "Missing collection_name, pipeline_id, or criteria_set_name"}
        ), 400

    collections_root = get_collections_dir()
    results = storage.list_evaluations(
        collections_root, collection_name, pipeline_id, criteria_set_name
    )
    if not results:
        return jsonify({"success": True, "deleted_count": 0, "total_count": 0})

    deleted_count = 0
    for item in results:
        artifact_id = item.get("artifact_id") or item.get("filename")
        if not artifact_id:
            continue
        if storage.delete_evaluation(
            collections_root,
            collection_name,
            artifact_id,
            pipeline_id,
            criteria_set_name,
        ):
            deleted_count += 1

    return jsonify(
        {
            "success": deleted_count == len(results),
            "deleted_count": deleted_count,
            "total_count": len(results),
        }
    )


@checklist_review_bp.get("/api/outputs")
def api_list_outputs():
    """List files in the outputs/ folder for the selected collection, process, checklist, and paper."""
    collection_name = request.args.get("collection_name")
    pipeline_id = request.args.get("pipeline_id")
    criteria_set_name = request.args.get("criteria_set_name")
    artifact_id = request.args.get("artifact_id")
    if not all([collection_name, pipeline_id, criteria_set_name, artifact_id]):
        return jsonify(
            {
                "error": "Missing collection_name, pipeline_id, criteria_set_name, or artifact_id"
            }
        ), 400
    collections_root = Path(get_collections_dir())
    items = storage.list_review_outputs(
        collections_root, collection_name, pipeline_id, criteria_set_name, artifact_id
    )
    return jsonify(items)


@checklist_review_bp.get("/api/outputs/token_usage")
def api_get_token_usage():
    """Return token_usage.json for the given collection, process, checklist, and paper."""
    collection_name = request.args.get("collection_name")
    pipeline_id = request.args.get("pipeline_id")
    criteria_set_name = request.args.get("criteria_set_name")
    artifact_id = request.args.get("artifact_id")
    if not all([collection_name, pipeline_id, criteria_set_name, artifact_id]):
        return jsonify(
            {
                "error": "Missing collection_name, pipeline_id, criteria_set_name, or artifact_id"
            }
        ), 400
    collections_root = Path(get_collections_dir())
    paper_dir = storage.get_review_paper_dir(
        collections_root, collection_name, pipeline_id, criteria_set_name, artifact_id
    )
    if not paper_dir:
        return jsonify({"error": "Paper folder not found"}), 404
    token_usage_path = paper_dir / "token_usage.json"
    if not token_usage_path.is_file():
        return jsonify(
            {
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "by_model": {},
            }
        )
    try:
        with open(token_usage_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except (json.JSONDecodeError, OSError):
        return jsonify({"error": "Failed to read token usage"}), 500


@checklist_review_bp.get("/api/outputs/token_usage/collection_summary")
def api_get_collection_token_usage_summary():
    """Return aggregated token usage across all reviewed papers for a collection/process/checklist."""
    collection_name = request.args.get("collection_name")
    pipeline_id = request.args.get("pipeline_id")
    criteria_set_name = request.args.get("criteria_set_name")
    if not all([collection_name, pipeline_id, criteria_set_name]):
        return jsonify(
            {"error": "Missing collection_name, pipeline_id, or criteria_set_name"}
        ), 400

    collections_root = Path(get_collections_dir())
    reviewed_results = storage.list_evaluations(
        collections_root,
        collection_name,
        pipeline_id,
        criteria_set_name,
    )

    summary: Dict[str, Any] = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "by_model": {},
        "reviewed_papers": len(reviewed_results),
        "papers_with_token_data": 0,
        "papers_missing_token_data": 0,
    }

    for item in reviewed_results:
        artifact_id = item.get("artifact_id")
        if not artifact_id:
            continue

        paper_dir = storage.get_review_paper_dir(
            collections_root,
            collection_name,
            pipeline_id,
            criteria_set_name,
            artifact_id,
        )
        if not paper_dir:
            summary["papers_missing_token_data"] += 1
            continue

        token_usage_path = paper_dir / "token_usage.json"
        if not token_usage_path.is_file():
            summary["papers_missing_token_data"] += 1
            continue

        try:
            with token_usage_path.open("r", encoding="utf-8") as f:
                token_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            summary["papers_missing_token_data"] += 1
            continue

        summary["papers_with_token_data"] += 1
        summary["total_input_tokens"] += int(
            token_data.get("total_input_tokens", 0) or 0
        )
        summary["total_output_tokens"] += int(
            token_data.get("total_output_tokens", 0) or 0
        )
        summary["total_tokens"] += int(token_data.get("total_tokens", 0) or 0)

        by_model = token_data.get("by_model") or {}
        if isinstance(by_model, dict):
            for model_id, values in by_model.items():
                if model_id not in summary["by_model"]:
                    summary["by_model"][model_id] = {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                    }

                model_totals = summary["by_model"][model_id]
                model_totals["input_tokens"] += int(values.get("input_tokens", 0) or 0)
                model_totals["output_tokens"] += int(
                    values.get("output_tokens", 0) or 0
                )
                model_totals["total_tokens"] += int(values.get("total_tokens", 0) or 0)

    return jsonify(summary)


@checklist_review_bp.get("/api/outputs/file")
def api_serve_output_file():
    """Serve a single file from the outputs/ folder. Use ?download=1 for attachment."""
    collection_name = request.args.get("collection_name")
    pipeline_id = request.args.get("pipeline_id")
    criteria_set_name = request.args.get("criteria_set_name")
    artifact_id = request.args.get("artifact_id")
    filename = request.args.get("filename")
    if not all(
        [collection_name, pipeline_id, criteria_set_name, artifact_id, filename]
    ):
        return jsonify({"error": "Missing required query parameters"}), 400
    if "/" in filename or "\\" in filename or filename.startswith("."):
        return jsonify({"error": "Invalid filename"}), 400
    collections_root = Path(get_collections_dir())
    outputs_dir = storage.get_review_outputs_dir(
        collections_root, collection_name, pipeline_id, criteria_set_name, artifact_id
    )
    if not outputs_dir:
        return jsonify({"error": "Outputs folder not found"}), 404
    file_path = (outputs_dir / filename).resolve()
    try:
        file_path.relative_to(outputs_dir.resolve())
    except ValueError:
        return jsonify({"error": "File not found"}), 404
    if not file_path.is_file():
        return jsonify({"error": "File not found"}), 404
    as_attachment = request.args.get("download") == "1"
    return send_file(file_path, as_attachment=as_attachment, download_name=filename)


@checklist_review_bp.post("/api/start-review")
def api_start_review():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request. Please try again."}), 400

        collection_name = data.get("collection_name")
        pipeline_id = data.get("pipeline_id")
        criteria_set_name = data.get("criteria_set_name")

        logger.info(
            f"Start review request: collection={collection_name}, pipeline={pipeline_id}, criteria_set={criteria_set_name}"
        )

        if not collection_name:
            return jsonify({"error": "Please select a collection first."}), 400
        if not pipeline_id:
            return jsonify({"error": "Please select a pipeline first."}), 400
        if not criteria_set_name:
            return jsonify({"error": "Please select a criteria set first."}), 400

        collections_root = get_collections_dir()
        collections_root_path = Path(collections_root)

        task_manager = TaskManager()
        # Sync any task that ran in a subprocess and has finished: the subprocess writes
        # status to file but the parent's in-memory task stays RUNNING until we reconcile.
        for task in task_manager.get_tasks_for_collection(collection_name):
            if task.progress.status != TaskStatus.RUNNING:
                continue
            process = getattr(task, "process", None)
            if process is None or process.is_alive():
                continue
            file_progress = task_persistence.read_progress(
                collections_root_path, task.task_id
            )
            if file_progress:
                task.progress.current = file_progress.get(
                    "current", task.progress.current
                )
                task.progress.total = file_progress.get("total", task.progress.total)
                task.progress.current_item = file_progress.get("current_item", "")
                status_val = file_progress.get("status", "running")
                task.progress.status = (
                    TaskStatus(status_val)
                    if isinstance(status_val, str)
                    else status_val
                )
                task.progress.error = file_progress.get("error")
                # Process exited but file may still say "running" if subprocess crashed before writing final status
                if task.progress.status == TaskStatus.RUNNING:
                    task.progress.status = TaskStatus.FAILED
                    task.progress.error = (
                        task.progress.error or "Process exited unexpectedly"
                    )
                if file_progress.get("started_at"):
                    try:
                        task.progress.started_at = datetime.fromisoformat(
                            file_progress["started_at"].replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        pass
                if file_progress.get("completed_at"):
                    try:
                        task.progress.completed_at = datetime.fromisoformat(
                            file_progress["completed_at"].replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        pass
                task.progress.results = file_progress.get("results", [])
                task.progress.log_messages = file_progress.get("log_messages", [])
                logger.info(
                    f"Synced task {task.task_id} from file: status={task.progress.status.value}"
                )

        running_task = task_manager.get_running_task_for_collection(collection_name)
        if running_task:
            return jsonify(
                {
                    "error": "A review is already in progress for this collection. Please wait for it to complete or stop it first.",
                    "task_id": running_task.task_id,
                }
            ), 400

        selected_artifacts = storage.list_selected_files(
            collections_root, collection_name
        )
        logger.info(f"Found {len(selected_artifacts)} papers in collection")

        if pipeline_id:
            results = storage.list_evaluations(
                collections_root, collection_name, pipeline_id, criteria_set_name
            )
            processed_set = {r.get("filename") for r in results if r.get("filename")}
            selected_artifacts = [
                p for p in selected_artifacts if p.get("filename") not in processed_set
            ]
            logger.info(f"After filtering, {len(selected_artifacts)} papers to process")

        if not selected_artifacts:
            total_papers = storage.list_selected_files(
                collections_root, collection_name
            )
            if len(total_papers) == 0:
                return jsonify(
                    {
                        "error": "No papers found in this collection. Please add papers first."
                    }
                ), 400
            else:
                return jsonify(
                    {
                        "error": "All papers in this collection have already been reviewed. Please add new papers or select a different collection."
                    }
                ), 400

        task_id = task_manager.create_task(
            collection_name=collection_name,
            pipeline_id=pipeline_id,
            criteria_set_name=criteria_set_name,
            artifacts=selected_artifacts,
        )

        logger.info(f"Created task {task_id} with {len(selected_artifacts)} artifacts")

        task = task_manager.get_task(task_id)
        if task:
            task_persistence.write_task_payload(
                collections_root,
                task_id,
                collection_name=task.collection_name,
                pipeline_id=task.pipeline_id,
                criteria_set_name=task.criteria_set_name,
                artifacts=task.artifacts,
                progress={
                    "current": task.progress.current,
                    "total": task.progress.total,
                    "current_item": task.progress.current_item,
                    "status": task.progress.status.value,
                    "error": task.progress.error,
                    "started_at": task.progress.started_at.isoformat()
                    if task.progress.started_at
                    else None,
                    "completed_at": task.progress.completed_at.isoformat()
                    if task.progress.completed_at
                    else None,
                    "results": task.progress.results,
                    "log_messages": task.progress.log_messages,
                },
            )
            task.progress.status = TaskStatus.RUNNING
            task.process = multiprocessing.Process(
                target=run_review_subprocess,
                args=(task_id, str(collections_root)),
                daemon=False,
            )
            task.process.start()
            logger.info(f"Started background process for task {task_id}")
        else:
            logger.error(f"Failed to get task {task_id} after creation")
            return jsonify(
                {"error": "Unable to start the review process. Please try again."}
            ), 500

        return jsonify(
            {
                "task_id": task_id,
                "message": "Review process started",
                "total_papers": len(selected_artifacts),
            }
        )
    except Exception as e:
        logger.error(f"Error in api_start_review: {e}", exc_info=True)
        return jsonify(
            {"error": "An error occurred while starting the review. Please try again."}
        ), 500


@checklist_review_bp.get("/api/review-status/<task_id>")
def api_review_status(task_id):
    try:
        logger.info(f"Status request received for task: {task_id}")
        task_manager = TaskManager()
        collections_root = get_collections_dir()
        task = task_manager.get_task(task_id)
        if not task:
            task = task_persistence.task_view_from_file(Path(collections_root), task_id)
        logger.debug(f"Task retrieved: {task is not None}")

        if not task:
            logger.warning(f"Status request for non-existent task: {task_id}")
            return jsonify(
                {
                    "error": "Review process not found. It may have been completed or stopped."
                }
            ), 404

        progress = task.progress
        if (
            getattr(task, "process", None) is not None
            and progress.status == TaskStatus.RUNNING
        ):
            file_progress = task_persistence.read_progress(
                Path(collections_root), task_id
            )
            if file_progress:
                progress = task_persistence.TaskView(task_id, file_progress).progress

        log_messages = []
        if progress.log_messages:
            for msg in progress.log_messages:
                if isinstance(msg, dict):
                    log_messages.append(
                        {
                            "timestamp": str(msg.get("timestamp", "")),
                            "message": str(msg.get("message", "")),
                            "level": str(msg.get("level", "info")),
                        }
                    )

        results = []
        if progress.results:
            for result in progress.results:
                if isinstance(result, dict):
                    results.append(
                        {
                            "artifact_id": str(result.get("artifact_id", "")),
                            "filename": str(result.get("filename", "")),
                            "status": str(result.get("status", "")),
                            "error": str(result.get("error", ""))
                            if result.get("error")
                            else None,
                        }
                    )

        logger.info(
            f"Status request for task {task_id}: status={progress.status.value}, logs={len(log_messages)}, current={progress.current}/{progress.total}"
        )

        response_data = {
            "task_id": task_id,
            "status": progress.status.value,
            "current": progress.current,
            "total": progress.total,
            "current_item": str(progress.current_item) if progress.current_item else "",
            "error": str(progress.error) if progress.error else None,
            "started_at": progress.started_at.isoformat()
            if progress.started_at and hasattr(progress.started_at, "isoformat")
            else (progress.started_at if progress.started_at else None),
            "completed_at": progress.completed_at.isoformat()
            if progress.completed_at and hasattr(progress.completed_at, "isoformat")
            else (progress.completed_at if progress.completed_at else None),
            "results": results,
            "log_messages": log_messages,
        }

        logger.debug(
            f"Returning status response for task {task_id}, response size: {len(str(response_data))} chars"
        )
        response = jsonify(response_data)
        logger.debug("Response created, returning...")
        return response
    except Exception as e:
        logger.error(f"Error getting task status: {e}", exc_info=True)
        return jsonify(
            {"error": "Unable to retrieve review status. Please try again."}
        ), 500


@checklist_review_bp.get("/api/review-status")
def api_review_status_for_collection():
    collection_name = request.args.get("collection_name")
    if not collection_name:
        return jsonify({"error": "Missing collection_name"}), 400

    task_manager = TaskManager()
    task = task_manager.get_running_task_for_collection(collection_name)

    if not task:
        return jsonify(
            {
                "status": "not_running",
                "message": "No review process is currently running",
            }
        )

    progress = task.progress
    return jsonify(
        {
            "task_id": task.task_id,
            "status": progress.status.value,
            "current": progress.current,
            "total": progress.total,
            "current_item": progress.current_item,
            "error": progress.error,
            "started_at": progress.started_at.isoformat()
            if progress.started_at
            else None,
            "completed_at": progress.completed_at.isoformat()
            if progress.completed_at
            else None,
            "results": progress.results,
            "log_messages": progress.log_messages,
        }
    )


@checklist_review_bp.post("/api/stop-review/<task_id>")
@checklist_review_bp.get("/api/stop-review/<task_id>")
def api_stop_review(task_id):
    try:
        logger.info(f"Stop request received for task {task_id}")
        task_manager = TaskManager()
        collections_root = get_collections_dir()
        task = task_manager.get_task(task_id)
        if not task:
            task = task_persistence.task_view_from_file(Path(collections_root), task_id)
        if not task:
            logger.warning(f"Stop request for non-existent task: {task_id}")
            return jsonify(
                {
                    "error": "Review process not found. It may have already been completed or stopped."
                }
            ), 404

        logger.info(f"Task {task_id} current status: {task.progress.status.value}")

        if task.progress.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            logger.info(
                f"Task {task_id} cannot be stopped (status: {task.progress.status.value})"
            )
            return jsonify(
                {
                    "message": "The review process is already stopped or completed.",
                    "task_id": task_id,
                    "status": task.progress.status.value,
                }
            )

        if hasattr(task, "stop_event") and task.stop_event is not None:
            task.stop_event.set()
        task_persistence.request_stop(Path(collections_root), task_id)
        logger.info(f"Stop event set for task {task_id}")

        if (
            getattr(task, "stop_event", None) is not None
            and task.progress.status == TaskStatus.PENDING
        ):
            task.progress.status = TaskStatus.STOPPED
            task.progress.completed_at = datetime.now()
            logger.info(f"Task {task_id} marked as STOPPED (was PENDING)")

        status = task.progress.status.value
        logger.info(f"Task {task_id} status after stop: {status}")
        return jsonify(
            {"message": "Stop request sent", "task_id": task_id, "status": status}
        )
    except Exception as e:
        logger.error(f"Error stopping task {task_id}: {e}", exc_info=True)
        return jsonify(
            {"error": "An error occurred while stopping the review. Please try again."}
        ), 500


@checklist_review_bp.post("/api/stop-review")
@checklist_review_bp.get("/api/stop-review")
def api_stop_review_for_collection():
    collection_name = request.args.get("collection_name")
    if not collection_name:
        return jsonify({"error": "Missing collection_name"}), 400

    task_manager = TaskManager()
    collections_root = Path(get_collections_dir())
    for t in task_manager.get_tasks_for_collection(collection_name):
        if t.progress.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            task_persistence.request_stop(collections_root, t.task_id)
    stopped_count = task_manager.stop_all_tasks_for_collection(collection_name)

    if stopped_count == 0:
        return jsonify(
            {"error": "No review process is currently running for this collection."}
        ), 404

    return jsonify(
        {
            "message": f"Stopped {stopped_count} review process(es)",
            "stopped_count": stopped_count,
        }
    )


def _run_review_process_background(task_id: str, collections_root):
    task_manager = TaskManager()

    try:
        logger.info(f"Background thread function called for task {task_id}")
        task = task_manager.get_task(task_id)

        if not task:
            logger.error(f"Task {task_id} not found in task manager")
            return

        if task.stop_event.is_set():
            logger.info(f"Task {task_id} was stopped before execution started")
            task.progress.status = TaskStatus.STOPPED
            task.progress.completed_at = datetime.now()
            return

        logger.info(f"Task found: {task_id}, papers: {len(task.artifacts)}")
        task.progress.status = TaskStatus.RUNNING
        logger.info(f"Task status set to RUNNING for {task_id}")

        def add_log_message(message: str, level: str = "info"):
            try:
                if task:
                    task.progress.log_messages.append(
                        {
                            "timestamp": datetime.now().isoformat(),
                            "message": message,
                            "level": level,
                        }
                    )
            except Exception as e:
                logger.error(f"Error adding log message: {e}", exc_info=True)

        criteria_set_name = task.criteria_set_name
        if criteria_set_name and (
            "/" in criteria_set_name or "\\" in criteria_set_name
        ):
            from pathlib import Path

            checklist_path = Path(criteria_set_name)
            criteria_set_name = checklist_path.stem

        try:
            review_process_def = build_review_process_definition(task.pipeline_id)
        except Exception as e:
            logger.error(f"Error loading pipeline: {e}", exc_info=True)
            add_log_message(f"Error: Failed to load pipeline: {str(e)}", "error")
            raise

        for idx, artifact in enumerate(task.artifacts):
            if task.stop_event.is_set():
                task.progress.status = TaskStatus.STOPPED
                task.progress.completed_at = datetime.now()
                logger.info(
                    f"Task {task_id} stopped at paper {idx + 1}/{len(task.artifacts)}"
                )
                return

            artifact_name = artifact.get("filename")
            if not artifact_name:
                continue

            task.progress.current = idx
            task.progress.current_item = artifact_name

            try:
                process_instance = ReviewProcess(
                    review_process_def,
                    stop_event=task.stop_event,
                    log_callback=add_log_message,
                    collections_root=collections_root,
                )
                run_result = process_instance.execute(
                    collection_name=task.collection_name,
                    artifact_name=artifact_name,
                    criteria_set_name=criteria_set_name,
                    artifact_index=idx + 1,
                    total_artifacts=len(task.artifacts),
                )
                if task.stop_event.is_set():
                    task.progress.status = TaskStatus.STOPPED
                    task.progress.completed_at = datetime.now()
                    logger.info(
                        f"Task {task_id} stopped after completing {artifact_name}"
                    )
                    return
                result_summary = {
                    "artifact_id": artifact.get("artifact_id", artifact_name),
                    "filename": artifact_name,
                    "status": "completed",
                }
                if run_result and run_result.get("token_usage"):
                    result_summary["token_usage"] = run_result["token_usage"]
                task.progress.results.append(result_summary)
            except InterruptedError as e:
                logger.info(
                    f"Task {task_id} interrupted during execution of {artifact_name}: {e}"
                )
                task.progress.status = TaskStatus.STOPPED
                task.progress.completed_at = datetime.now()
                add_log_message("Review stopped by user", "warning")
                result_summary = {
                    "artifact_id": artifact.get("artifact_id", artifact_name),
                    "filename": artifact_name,
                    "status": "stopped",
                    "error": "Stopped by user",
                }
                task.progress.results.append(result_summary)
                return
            except Exception as e:
                logger.error(f"Failed to process {artifact_name}: {e}", exc_info=True)
                add_log_message(f"Error processing paper: {str(e)}", "error")
                result_summary = {
                    "artifact_id": artifact.get("artifact_id", artifact_name),
                    "filename": artifact_name,
                    "status": "failed",
                    "error": str(e),
                }
                task.progress.results.append(result_summary)

                if task.stop_event.is_set():
                    task.progress.status = TaskStatus.STOPPED
                    task.progress.completed_at = datetime.now()
                    logger.info(
                        f"Task {task_id} stopped after error on {artifact_name}"
                    )
                    return

        task.progress.status = TaskStatus.COMPLETED
        task.progress.current = len(task.artifacts)
        task.progress.completed_at = datetime.now()
        logger.info(f"Task {task_id} completed successfully")

    except Exception as e:
        logger.error(f"Task {task_id} failed with exception: {e}", exc_info=True)
        try:
            task_manager = TaskManager()
            task = task_manager.get_task(task_id)
            if task:
                task.progress.status = TaskStatus.FAILED
                task.progress.error = str(e)
                task.progress.completed_at = datetime.now()
                if hasattr(task.progress, "log_messages"):
                    task.progress.log_messages.append(
                        {
                            "timestamp": datetime.now().isoformat(),
                            "message": f"Task failed: {str(e)}",
                            "level": "error",
                        }
                    )
                logger.info(f"Task {task_id} marked as FAILED")
            else:
                logger.error(f"Could not find task {task_id} to mark as failed")
        except Exception as inner_e:
            logger.error(
                f"Error updating task status after failure: {inner_e}", exc_info=True
            )
