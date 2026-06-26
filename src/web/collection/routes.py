from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from flask import (
    Blueprint,
    Response,
    flash,
    jsonify,
    render_template,
    request,
    stream_with_context,
)

from src.core import storage, system, visualizer
from src.core.pdf_processing import (
    PaperProcessingError,  # Alias for backward compatibility
    PDFProcessingError,
    extract_first_page,
    extract_metadata_from_first_page,
    get_default_llm_provider,
    is_rule_based_pdf_metadata_extraction,
    pdf_to_markdown,
)
from src.core.workspace import get_collections_dir
from src.web.collection import services

collection_bp = Blueprint(
    "collection", __name__, url_prefix="/collection", template_folder="templates"
)


@collection_bp.route("/static/<path:filename>")
def collection_static(filename):
    from flask import send_from_directory

    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    static_dir = base_dir / "src" / "web" / "collection" / "static"
    return send_from_directory(str(static_dir), filename)


def _sse_message(event: str, payload: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def _enrich_collection_with_metadata(
    collections_root: Path, collection_name: str, collection_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Enrich collection papers with metadata from source/metadata JSON files.
    This allows collection.json to stay minimal while still providing metadata to the frontend.
    """
    collection_dir = storage._collection_dir(
        collections_root, collection_name, create=False
    )
    meta_dir = storage._source_metadata_dir(collection_dir, create=False)

    def paper_stem_from_id(pid):
        return Path(pid).stem if pid else ""

    enriched_papers = []
    for paper in collection_data.get("papers", []):
        paper_id = paper.get("paper_id")
        if not paper_id:
            enriched_papers.append(paper)
            continue
        stem = paper_stem_from_id(paper_id)
        json_path = (meta_dir / f"{stem}.json") if meta_dir.exists() else None
        if not json_path or not json_path.exists():
            json_path = collection_dir / "source_extracted" / f"{stem}.json"
        enriched_paper = paper.copy()

        # Resolve file_path relative to collection_dir to create absolute path for URL
        file_path_rel = paper.get("file_path", "")
        if file_path_rel:
            if Path(file_path_rel).is_absolute():
                absolute_file_path = file_path_rel
            else:
                absolute_file_path = str((collection_dir / file_path_rel).resolve())
        else:
            pdf_dir = storage._source_pdf_dir(collection_dir, create=False)
            if pdf_dir.exists():
                absolute_file_path = str(
                    (pdf_dir / paper.get("filename", "")).resolve()
                )
            else:
                absolute_file_path = str(
                    (collection_dir / "source" / paper.get("filename", "")).resolve()
                )

        if json_path.exists():
            try:
                with json_path.open("r", encoding="utf-8") as f:
                    metadata = json.load(f)
                    # Add metadata fields for frontend compatibility
                    enriched_paper["title"] = metadata.get("title", paper_id)
                    enriched_paper["abstract"] = metadata.get("abstract", "")
                    enriched_paper["summary"] = metadata.get(
                        "abstract", ""
                    )  # Alias for compatibility
                    enriched_paper["authors"] = metadata.get("authors", [])
                    enriched_paper["arxiv_id"] = paper_id  # For compatibility
                    enriched_paper["preview"] = (
                        (metadata.get("abstract", "")[:320] + "…")
                        if len(metadata.get("abstract", "")) > 320
                        else metadata.get("abstract", "")
                    )
                    enriched_paper["url"] = f"file://{absolute_file_path}"
            except Exception:
                # If loading fails, use defaults
                enriched_paper["title"] = paper_id
                enriched_paper["abstract"] = ""
                enriched_paper["summary"] = ""
                enriched_paper["authors"] = []
                enriched_paper["arxiv_id"] = paper_id
                enriched_paper["preview"] = ""
                enriched_paper["url"] = f"file://{absolute_file_path}"
        else:
            # No metadata file, use defaults
            enriched_paper["title"] = paper_id
            enriched_paper["abstract"] = ""
            enriched_paper["summary"] = ""
            enriched_paper["authors"] = []
            enriched_paper["arxiv_id"] = paper_id
            enriched_paper["preview"] = ""
            enriched_paper["url"] = f"file://{absolute_file_path}"

        enriched_papers.append(enriched_paper)

    collection_data["papers"] = enriched_papers
    return collection_data


def _regenerate_visualization(
    collections_root: Path, collection_name: str, model: str | None = None
) -> None:
    try:
        collection = storage.load_collection(collections_root, collection_name)
        if not collection or not collection.get("papers"):
            return
        # Enrich with metadata for visualization
        collection = _enrich_collection_with_metadata(
            collections_root, collection_name, collection
        )
        # Pass collections_root to visualizer
        collection["_collections_root"] = str(collections_root)
        viz_result = visualizer.visualize_collection(collection, model=model)
        storage.save_plot(collections_root, collection_name, viz_result["plot"])
    except Exception:
        pass


@collection_bp.route("/", methods=["GET", "POST"])
def index():
    collections_root = get_collections_dir()

    context: Dict[str, Any] = {
        "active_tab": "collection",
        "collection_result": None,
        "visualization_result": None,
        "embedding_models": [],
        "viz_status": None,
    }

    collections = storage.list_collections(collections_root)
    collections = [c for c in collections if c.get("name") != "Temporary"]

    preferred_model = "mxbai-embed-large:latest"
    try:
        models = visualizer.list_available_models()
        if preferred_model not in models:
            models = [preferred_model, *models]
        context["embedding_models"] = models
        context["selected_embed_model"] = preferred_model
    except visualizer.VisualizationError:
        context["embedding_models"] = [preferred_model]
        context["selected_embed_model"] = preferred_model

    if collections and context["collection_result"] is None:
        collection_arg = request.args.get("collection")
        if collection_arg:
            collection_data = storage.load_collection(collections_root, collection_arg)
            if collection_data:
                # Enrich papers with metadata from source_extracted JSON files
                collection_data = _enrich_collection_with_metadata(
                    collections_root, collection_arg, collection_data
                )
                context["collection_result"] = collection_data
                if context["collection_result"]:
                    viz_data = storage.load_plot(collections_root, collection_arg)
                    if viz_data and "plot" in viz_data:
                        context["visualization_result"] = viz_data
                        context["viz_status"] = storage.get_visualization_status(
                            collections_root, collection_arg
                        )
                    else:
                        try:
                            # Pass collections_root for metadata loading
                            context["collection_result"]["_collections_root"] = str(
                                collections_root
                            )
                            viz_result = visualizer.visualize_collection(
                                context["collection_result"],
                                model=context["selected_embed_model"],
                            )
                            storage.save_plot(
                                collections_root, collection_arg, viz_result["plot"]
                            )
                            context["visualization_result"] = viz_result
                            context["viz_status"] = {
                                "status": "ok",
                                "message": "Just generated.",
                            }
                        except visualizer.VisualizationError:
                            context["viz_status"] = storage.get_visualization_status(
                                collections_root, collection_arg
                            )

    if request.method == "POST":
        form_id = request.form.get("form_id")
        try:
            if form_id == "abstract_form":
                folder_path = request.form.get("folder_path", "")
                result = services.process_collection(folder_path)
                result["selected_files"] = storage.load_selected_list(
                    collections_root, result["collection_name"]
                )
                payload = {
                    "generated_at": datetime.utcnow().isoformat(),
                    **result,
                }
                storage.save_collection(
                    collections_root, result["collection_name"], payload
                )
                _regenerate_visualization(
                    collections_root,
                    result["collection_name"],
                    context.get("selected_embed_model"),
                )
                # Enrich with metadata for display
                result = _enrich_collection_with_metadata(
                    collections_root, result["collection_name"], result
                )
                context["collection_result"] = result
                flash(f"Indexed {len(result['papers'])} local PDFs.", "success")

            elif form_id == "visualize_form":
                collection_choice = (
                    request.form.get("collection_choice")
                    or request.form.get("collection_name")
                    or ""
                )
                collection_payload = storage.load_collection(
                    collections_root, collection_choice
                )
                if not collection_payload:
                    raise visualizer.VisualizationError(
                        "Unable to find the selected collection."
                    )
                # Enrich with metadata
                collection_payload = _enrich_collection_with_metadata(
                    collections_root, collection_choice, collection_payload
                )
                collection_payload["_collections_root"] = str(collections_root)
                model_choice = request.form.get("embed_model") or None
                viz_result = visualizer.visualize_collection(
                    collection_payload, model=model_choice
                )
                storage.save_plot(
                    collections_root,
                    collection_payload["collection_name"],
                    viz_result["plot"],
                )
                context["visualization_result"] = viz_result
                context["collection_result"] = collection_payload
                context["selected_embed_model"] = viz_result["model"]
                context["viz_status"] = {"status": "ok", "message": "Just generated."}
                flash("Generated embedding projection via Ollama.", "success")

        except PaperProcessingError as err:
            flash(str(err), "danger")
        except visualizer.VisualizationError as err:
            flash(str(err), "danger")
        except ValueError as err:
            flash(str(err), "danger")

    context["collections"] = collections
    return render_template("collection/index.html", **context)


@collection_bp.post("/api/collection/create")
def create_collection_route():
    collections_root = get_collections_dir()
    payload = request.get_json(silent=True) or {}
    name = payload.get("name")

    # If name is provided, check if it already exists
    if name:
        from src.core.storage import _slug

        existing_collections = storage.list_collections(collections_root)
        name_slug = _slug(name)
        for coll in existing_collections:
            coll_slug = coll.get("slug") or _slug(coll.get("name", ""))
            if coll_slug == name_slug:
                return jsonify(
                    {"error": "A collection with this name already exists"}
                ), 400

    name = storage.create_new_collection(collections_root, name)
    return jsonify({"name": name, "message": f"Collection '{name}' created."})


@collection_bp.put("/api/collection/<collection_name>/rename")
def rename_collection_route(collection_name: str):
    collections_root = get_collections_dir()
    payload = request.get_json(silent=True) or {}
    new_name = payload.get("new_name")
    if not new_name:
        return jsonify({"error": "New name required."}), 400

    from src.core.storage import _slug

    existing_collections = storage.list_collections(collections_root)
    new_name_slug = _slug(new_name)
    current_slug = _slug(collection_name)

    if new_name_slug != current_slug:
        for coll in existing_collections:
            coll_slug = coll.get("slug") or _slug(coll.get("name", ""))
            if coll_slug == new_name_slug and coll_slug != current_slug:
                return jsonify(
                    {"error": "A collection with this name already exists"}
                ), 400

    success = storage.rename_collection(collections_root, collection_name, new_name)
    if not success:
        return jsonify(
            {"error": "Rename failed (duplicate name or original not found)."}
        ), 400
    return jsonify({"message": f"Renamed to '{new_name}'."})


@collection_bp.post("/api/collection/<collection_name>/scan")
def scan_collection_route(collection_name: str):
    collections_root = get_collections_dir()
    collection = storage.load_collection(collections_root, collection_name)
    if not collection:
        return jsonify({"error": "Collection not found."}), 404

    collection_dir = storage._collection_dir(
        collections_root, collection_name, create=False
    )

    def generate():
        try:
            for event in services.iterate_collection(
                str(collection_dir), collection_name_override=collection_name
            ):
                if event["type"] == "progress":
                    yield _sse_message(
                        "progress",
                        {
                            "current": event["current"],
                            "total": event["total"],
                            "filename": event["filename"],
                        },
                    )
                elif event["type"] == "result":
                    # Save simplified collection (only paper_id, filename, file_path)
                    storage.save_collection(
                        collections_root,
                        collection_name,
                        {
                            "generated_at": datetime.utcnow().isoformat(),
                            **event["payload"],
                        },
                    )
                    _regenerate_visualization(collections_root, collection_name)
                    yield _sse_message(
                        "complete",
                        {
                            "collection": collection_name,
                            "paper_count": len(event["payload"]["papers"]),
                        },
                    )
        except PaperProcessingError as exc:
            yield _sse_message("error", {"message": str(exc)})
        except Exception as exc:  # pragma: no cover - safety
            yield _sse_message("error", {"message": f"Unexpected error: {exc}"})

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@collection_bp.post("/api/collection/<collection_name>/upload")
def upload_papers_route(collection_name: str):
    collections_root = get_collections_dir()
    collection = storage.load_collection(collections_root, collection_name)
    if not collection:
        return jsonify({"error": "Collection not found."}), 404

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files uploaded."}), 400

    # Check for LLM provider only when the selected extraction method needs one.
    provider_config = get_default_llm_provider()
    if provider_config is None and not is_rule_based_pdf_metadata_extraction():
        return jsonify(
            {
                "error": "No LLM provider configured. Please add an LLM provider in settings or use rule-based PDF metadata extraction."
            }
        ), 400

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
                # else: markdown already exists, skip to metadata

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
                # else: metadata already exists

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

            # Update collection after processing
            try:
                # Re-scan to update papers list with newly processed PDFs
                for event in services.iterate_collection(
                    str(collection_dir), collection_name_override=collection_name
                ):
                    if event["type"] == "result":
                        storage.save_collection(
                            collections_root,
                            collection_name,
                            {
                                "generated_at": datetime.utcnow().isoformat(),
                                **event["payload"],
                            },
                        )
                        _regenerate_visualization(collections_root, collection_name)
                        break
            except Exception:
                pass  # Continue even if collection update fails

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


@collection_bp.post("/api/folder-picker")
def folder_picker():
    try:
        selection = system.choose_directory()
    except system.FolderSelectionError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(
        {"path": selection.path, "collection_name": selection.collection_name}
    )


@collection_bp.post("/api/process-pdfs")
def process_pdfs():
    collections_root = get_collections_dir()
    payload = request.get_json(silent=True) or {}

    folder_path = (payload.get("folder_path") or "").strip()
    collection_choice = (payload.get("collection_choice") or "").strip()

    if not folder_path and collection_choice:
        target_dir = Path(collections_root) / collection_choice
        if target_dir.is_dir():
            folder_path = str(target_dir)
        else:
            return jsonify(
                {"error": f"Collection '{collection_choice}' not found."}
            ), 400

    def generate():
        try:
            for event in services.iterate_collection(folder_path):
                if event["type"] == "progress":
                    yield _sse_message(
                        "progress",
                        {
                            "current": event["current"],
                            "total": event["total"],
                            "filename": event["filename"],
                        },
                    )
                elif event["type"] == "result":
                    collection_name_from_event = event["payload"]["collection_name"]
                    # Save simplified collection (only paper_id, filename, file_path)
                    storage.save_collection(
                        collections_root,
                        collection_name_from_event,
                        {
                            "generated_at": datetime.utcnow().isoformat(),
                            **event["payload"],
                        },
                    )
                    _regenerate_visualization(
                        collections_root, collection_name_from_event
                    )
                    yield _sse_message(
                        "complete",
                        {
                            "collection": collection_name_from_event,
                            "paper_count": len(event["payload"]["papers"]),
                        },
                    )
        except PaperProcessingError as exc:
            yield _sse_message("error", {"message": str(exc)})
        except Exception as exc:  # pragma: no cover - safety
            yield _sse_message("error", {"message": f"Unexpected error: {exc}"})

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@collection_bp.post("/api/export-selection")
def export_selection():
    payload = request.get_json(silent=True) or {}

    collection_name = payload.get("collection_name")
    files = payload.get("files")

    collections_root = get_collections_dir()

    if not collection_name or not isinstance(files, list):
        return jsonify({"error": "Collection name and file list are required."}), 400

    entries = []
    for item in files:
        if isinstance(item, dict):
            filename = item.get("filename") or item.get("paper_id") or item.get("title")
            if not filename:
                continue
            entries.append(
                {
                    "filename": filename,
                    "paper_id": item.get("paper_id"),
                    "title": item.get("title"),
                    "url": item.get("url"),
                }
            )
        elif isinstance(item, str):
            entries.append({"filename": item, "title": item, "paper_id": item})

    try:
        export_path = storage.save_selected_list(
            collections_root, collection_name, entries
        )
    except Exception as exc:
        return jsonify({"error": f"Unable to save selection: {exc}"}), 500

    return jsonify({"message": f"Selection updated at {export_path}."})


@collection_bp.delete("/api/collection/<collection_name>")
def delete_collection_route(collection_name: str):
    collections_root = get_collections_dir()
    success = storage.delete_collection(collections_root, collection_name)
    if not success:
        return jsonify({"error": "Collection not found or unable to delete."}), 404
    return jsonify({"message": f"Collection '{collection_name}' deleted."})


@collection_bp.delete("/api/collection/<collection_name>/paper/<paper_id>")
def delete_paper_route(collection_name: str, paper_id: str):
    collections_root = get_collections_dir()
    success = storage.remove_paper(collections_root, collection_name, paper_id)
    if not success:
        return jsonify({"error": "Paper not found or unable to delete."}), 404
    return jsonify({"message": f"Paper '{paper_id}' removed from collection."})


@collection_bp.delete("/api/collection/<collection_name>/papers")
def delete_all_papers_route(collection_name: str):
    collections_root = get_collections_dir()
    collection = storage.load_collection(collections_root, collection_name)
    if not collection:
        return jsonify({"error": "Collection not found."}), 404

    paper_count = len(collection.get("papers", []))
    success = storage.remove_all_papers(collections_root, collection_name)
    if not success:
        return jsonify({"error": "Unable to delete papers."}), 500

    return jsonify(
        {
            "message": f"Deleted {paper_count} paper(s) from collection.",
            "deleted_count": paper_count,
        }
    )
