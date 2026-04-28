from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from src.core.workspace import get_collections_dir
from flask import Blueprint, abort, current_app, flash, render_template, request, send_file, jsonify, send_from_directory, Response, stream_with_context

from src.web.human_verification import services
from src.core import storage

human_verification_bp = Blueprint("human_verification", __name__, url_prefix="/human_verification", template_folder="templates")


@human_verification_bp.route("/static/<path:filename>")
def human_verification_static(filename):
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    static_dir = base_dir / "src" / "web" / "human_verification" / "static"
    return send_from_directory(str(static_dir), filename)


@human_verification_bp.route("/", methods=["GET", "POST"])
def index():
    collections_root = get_collections_dir()
    context: Dict[str, Any] = {
        "active_tab": "human_verification",
        "review_payload": None,
        "selected_review_path": None,
    }

    collections_list = storage.list_collections(collections_root)
    context["collections"] = [
        {
            "name": item["name"],
            "slug": item.get("slug") or item["name"],
            "selected_files": []
        }
        for item in collections_list
    ]

    if request.method == "POST":
        form_id = request.form.get("form_id")
        
        if form_id == "save_verification":
            collection_name = request.form.get("collection_choice")
            process_name = request.form.get("process_choice")
            checklist_name = request.form.get("checklist_choice")
            paper_id = request.form.get("paper_id")
            verification_data = services.capture_verification_updates(request.form)
            
            if collection_name and process_name and paper_id:
                storage.save_human_verification(collections_root, collection_name, process_name, paper_id, verification_data, checklist_name)
                flash("Verification saved.", "success")
                
                paper_answers = storage.load_generated_answer(collections_root, collection_name, paper_id, process_name, checklist_name)
                existing_verification = storage.load_human_verification(collections_root, collection_name, process_name, paper_id, checklist_name)
                pdf_path = request.form.get("pdf_path", "")
                
                context["review_payload"] = {
                    "entries": services.prepare_review_view(paper_answers, existing_verification),
                    "pdf_path": pdf_path,
                    "collection": collection_name,
                    "process": process_name,
                    "checklist": checklist_name,
                    "paper_id": paper_id
                }
                context["selected_collection"] = collection_name
                context["selected_process"] = process_name
                context["selected_checklist"] = checklist_name
                context["selected_paper"] = paper_id

        elif form_id == "human_form":
            collection_choice = request.form.get("collection_choice", "")
            process_choice = request.form.get("process_choice", "")
            checklist_choice = request.form.get("checklist_choice", "")
            paper_choice = request.form.get("selected_file", "")
            
            if not collection_choice or not process_choice or not checklist_choice or not paper_choice:
                flash("Please choose a collection, process, checklist, and paper.", "warning")
            else:
                paper_answers = storage.load_generated_answer(collections_root, collection_choice, paper_choice, process_choice, checklist_choice)
                
                if not paper_answers:
                    flash("No automated answers found for this paper.", "danger")
                else:
                    existing_verification = storage.load_human_verification(collections_root, collection_choice, process_choice, paper_choice, checklist_choice)
                    pdf_path = f"{collection_choice}/source/pdf/{paper_choice}"
                    
                    context["review_payload"] = {
                        "entries": services.prepare_review_view(paper_answers, existing_verification),
                        "pdf_path": pdf_path,
                        "collection": collection_choice,
                        "process": process_choice,
                        "checklist": checklist_choice,
                        "paper_id": paper_choice
                    }
                    context["selected_collection"] = collection_choice
                    context["selected_process"] = process_choice
                    context["selected_checklist"] = checklist_choice
                    context["selected_paper"] = paper_choice

    return render_template("human_verification/index.html", **context)


@human_verification_bp.get("/api/processes")
def api_list_processes():
    """List all globally available process definitions"""
    from pathlib import Path
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    return jsonify(storage.list_global_processes(base_dir))

@human_verification_bp.get("/api/papers_with_results")
def api_list_papers_with_results():
    collection_name = request.args.get("collection_name")
    process_name = request.args.get("process_name")
    checklist_name = request.args.get("checklist_name")
    if not collection_name or not process_name:
        return jsonify([])
    collections_root = get_collections_dir()
    return jsonify(storage.list_generated_answers(collections_root, collection_name, process_name, checklist_name))

@human_verification_bp.get("/api/collections")
def api_list_collections():
    """List all collections"""
    collections_root = get_collections_dir()
    collections = storage.list_collections(collections_root)
    # Filter out Temporary collection
    collections = [c for c in collections if c.get("name") != "Temporary"]
    return jsonify(collections)

@human_verification_bp.get("/api/checklists")
def api_list_checklists():
    """List all checklists from workspaces/guest/checklists (global, not per collection)"""
    from pathlib import Path
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    all_checklists = storage.list_checklists(base_dir)
    from datetime import datetime
    all_checklists.sort(key=lambda x: x.get("created_at") if isinstance(x.get("created_at"), datetime) else datetime(1970, 1, 1), reverse=True)
    return jsonify(all_checklists)


def _sse_message(event: str, payload: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@human_verification_bp.post("/api/ground-truth-verify")
def api_ground_truth_verify():
    """Accept multiple ground-truth JSON files; compare to generated answers and save human_verification.json. Stream progress via SSE."""
    collection_name = request.form.get("collection_name", "").strip()
    process_name = request.form.get("process_name", "").strip()
    checklist_name = (request.form.get("checklist_name") or "").strip()
    if not collection_name or not process_name or not checklist_name:
        return jsonify({"error": "Missing collection, process, or checklist."}), 400

    files = request.files.getlist("files")
    json_files = [f for f in files if f and f.filename.lower().endswith(".json")]
    if not json_files:
        return jsonify({"error": "No JSON files selected."}), 400

    collections_root = Path(get_collections_dir())

    # Read all upload bodies before streaming the response. The SSE generator runs after the
    # view returns; Werkzeug may then close multipart FileStorage streams, causing
    # "I/O operation on closed file" if we call file.read() inside the generator.
    file_jobs: list[tuple[str, str | None, str | None]] = []
    for f in json_files:
        filename = f.filename or "unknown.json"
        try:
            gt_content = f.read()
            if isinstance(gt_content, bytes):
                gt_content = gt_content.decode("utf-8")
            file_jobs.append((filename, gt_content, None))
        except Exception as e:
            file_jobs.append((filename, None, str(e)))

    def generate():
        total = len(file_jobs)
        processed = 0
        skipped = 0
        errors = []
        try:
            for index, (filename, gt_text, read_err) in enumerate(file_jobs, start=1):
                stem = Path(filename).stem
                paper_id = stem + ".pdf"
                yield _sse_message(
                    "progress",
                    {
                        "current": index,
                        "total": total,
                        "paper_id": paper_id,
                        "filename": filename,
                        "message": f"Comparing {filename}...",
                    },
                )
                if read_err:
                    errors.append({"file": filename, "error": read_err})
                    yield _sse_message(
                        "progress",
                        {
                            "current": index,
                            "total": total,
                            "paper_id": paper_id,
                            "filename": filename,
                            "message": f"Error reading {filename}: {read_err}",
                            "error": True,
                        },
                    )
                    continue
                if not storage.process_result_exists(collections_root, collection_name, process_name, paper_id, checklist_name):
                    skipped += 1
                    yield _sse_message(
                        "progress",
                        {
                            "current": index,
                            "total": total,
                            "paper_id": paper_id,
                            "filename": filename,
                            "message": f"Skipped {filename} (no generated answers for this paper).",
                            "skipped": True,
                        },
                    )
                    continue
                try:
                    ground_truth_data = json.loads(gt_text)
                except Exception as e:
                    errors.append({"file": filename, "error": str(e)})
                    yield _sse_message(
                        "progress",
                        {
                            "current": index,
                            "total": total,
                            "paper_id": paper_id,
                            "filename": filename,
                            "message": f"Error reading {filename}: {e}",
                            "error": True,
                        },
                    )
                    continue
                generated_data = storage.load_generated_answer(collections_root, collection_name, paper_id, process_name, checklist_name)
                if not generated_data:
                    skipped += 1
                    yield _sse_message(
                        "progress",
                        {
                            "current": index,
                            "total": total,
                            "paper_id": paper_id,
                            "filename": filename,
                            "message": f"Skipped {filename} (no generated answers).",
                            "skipped": True,
                        },
                    )
                    continue
                verifications = services.compare_ground_truth_to_generated(ground_truth_data, generated_data)
                storage.save_human_verification(
                    collections_root,
                    collection_name,
                    process_name,
                    paper_id,
                    {"verifications": verifications},
                    checklist_name,
                )
                processed += 1
                yield _sse_message(
                    "progress",
                    {
                        "current": index,
                        "total": total,
                        "paper_id": paper_id,
                        "filename": filename,
                        "message": f"Verified {filename}.",
                        "processed": True,
                    },
                )
            yield _sse_message(
                "complete",
                {
                    "processed_count": processed,
                    "skipped_count": skipped,
                    "total": total,
                    "errors": errors,
                },
            )
        except Exception as exc:
            yield _sse_message("error", {"message": str(exc)})

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@human_verification_bp.get("/pdf")
def serve_pdf():
    path_param = request.args.get("path")
    if not path_param:
        abort(404)
    collections_root = Path(get_collections_dir()).resolve()
    target = (collections_root / path_param).resolve()
    
    try:
        target.relative_to(collections_root)
    except ValueError:
        abort(404)
    if not target.exists():
        abort(404)
    return send_file(target, mimetype="application/pdf")
